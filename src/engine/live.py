from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import csv
import json
from zoneinfo import ZoneInfo

from broker.alpaca_broker import AlpacaBroker
from broker.futu_broker import FutuBroker
from broker.sim_broker import SimBroker
from broker.base import BaseBroker
from config import AppConfig
from market.data import fetch_ohlcv
from strategy.selector import generate_signal_for_config
from utils.notify import send_webhook_alert


def _to_1d_close(close):
    if hasattr(close, "iloc") and hasattr(close, "ndim") and close.ndim == 2:
        return close.iloc[:, 0]
    return close


def build_broker(cfg: AppConfig) -> BaseBroker:
    """Select broker implementation by market."""
    if cfg.market == "US":
        # US dry-run can run without broker credentials.
        if cfg.dry_run and not cfg.alpaca_api_key:
            return SimBroker(initial_equity=cfg.initial_capital)
        return AlpacaBroker(
            api_key=cfg.alpaca_api_key,
            secret_key=cfg.alpaca_secret_key,
            paper=cfg.alpaca_paper,
        )
    if cfg.market == "HK":
        if cfg.hk_broker == "futu":
            return FutuBroker(host=cfg.futu_host, port=cfg.futu_port)
        # Default HK path is simulated broker so HK can run out-of-box.
        return SimBroker(initial_equity=cfg.initial_capital)
    raise ValueError(f"Unsupported market: {cfg.market}")


def run_live_once(cfg: AppConfig, symbol: str, target_position: int, current_position: int) -> None:
    """
    Simple one-shot execution example:
    - target_position=1 means hold one lot (qty=1)
    - target_position=0 means flat
    """
    broker = build_broker(cfg)
    try:
        delta = target_position - current_position
        if delta > 0:
            broker.submit_market_order(symbol=symbol, qty=delta, side="buy")
        elif delta < 0:
            broker.submit_market_order(symbol=symbol, qty=abs(delta), side="sell")
    finally:
        broker.close()


def _is_risk_allowed(last_price: float, qty: int, max_notional: float) -> bool:
    order_notional = abs(last_price * qty)
    return order_notional <= max_notional


def _append_trade_log(
    symbol: str,
    market: str,
    price: float,
    current_position: int,
    target_position: int,
    action: str,
    reason: str,
) -> None:
    """Append one decision/execution record for audit and debugging."""
    log_path = Path("logs") / "live_trades.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(
                [
                    "timestamp",
                    "market",
                    "symbol",
                    "price",
                    "current_position",
                    "target_position",
                    "action",
                    "reason",
                ]
            )
        writer.writerow(
            [
                datetime.utcnow().isoformat(),
                market,
                symbol,
                round(price, 4),
                current_position,
                target_position,
                action,
                reason,
            ]
        )


def run_live_cycle(cfg: AppConfig) -> None:
    """Run one full live decision cycle for all configured symbols."""
    broker = build_broker(cfg)
    try:
        if cfg.enable_market_hours_check:
            # Skip outside session to avoid accidental off-hours orders.
            market_open = _is_market_open(cfg, broker)
            if not market_open:
                print("[LIVE] Market is closed (including holidays), skip this cycle.")
                return

        risk_off = _is_daily_loss_circuit_breaker_triggered(cfg, broker)
        if risk_off:
            # After breaker trigger, strategy can only reduce risk (flatten).
            print("[LIVE] Daily loss circuit breaker triggered. Only flattening positions.")

        lookback_start = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
        lookback_end = datetime.utcnow().strftime("%Y-%m-%d")

        for symbol in cfg.symbols:
            df = fetch_ohlcv(symbol, cfg.market, lookback_start, lookback_end)
            close = _to_1d_close(df["close"])
            signal = generate_signal_for_config(close, cfg)
            if signal.empty:
                _append_trade_log(symbol, cfg.market, 0.0, 0, 0, "skip", "empty_signal")
                continue

            last_signal = int(signal.iloc[-1])  # 1 long, 0 flat
            last_price = float(close.iloc[-1])
            current_position = broker.get_position_qty(symbol)
            avg_entry_price = broker.get_position_avg_entry_price(symbol)
            stop_or_take_reason = _risk_exit_reason(
                current_position=current_position,
                avg_entry_price=avg_entry_price,
                last_price=last_price,
                stop_loss_pct=cfg.stop_loss_pct,
                take_profit_pct=cfg.take_profit_pct,
            )

            if risk_off:
                target_position = 0
                decision_reason = "daily_loss_circuit_breaker"
            elif stop_or_take_reason:
                target_position = 0
                decision_reason = stop_or_take_reason
            else:
                target_position = cfg.live_qty_per_trade if last_signal == 1 else 0
                decision_reason = "signal_rebalance"

            if not cfg.allow_short and target_position < 0:
                target_position = 0

            delta = target_position - current_position
            if delta == 0:
                _append_trade_log(
                    symbol,
                    cfg.market,
                    last_price,
                    current_position,
                    target_position,
                    "hold",
                    decision_reason if decision_reason != "signal_rebalance" else "already_at_target",
                )
                continue

            if not _is_risk_allowed(last_price, delta, cfg.max_notional_per_trade):
                # Hard cap on per-order notional.
                _append_trade_log(
                    symbol,
                    cfg.market,
                    last_price,
                    current_position,
                    target_position,
                    "blocked",
                    "max_notional_exceeded",
                )
                continue

            side = "buy" if delta > 0 else "sell"
            if side == "buy":
                # Buy-side cash check with a small safety buffer.
                order_notional = abs(last_price * delta)
                buying_power = broker.get_buying_power()
                min_required = order_notional + cfg.min_buying_power_buffer
                if buying_power < min_required:
                    _append_trade_log(
                        symbol,
                        cfg.market,
                        last_price,
                        current_position,
                        target_position,
                        "blocked",
                        "insufficient_buying_power",
                    )
                    print(
                        f"[LIVE] {symbol} blocked: buying_power={buying_power:.2f} "
                        f"required={min_required:.2f}"
                    )
                    continue

            if cfg.dry_run:
                # Dry-run executes full decision pipeline but skips broker order.
                _append_trade_log(
                    symbol,
                    cfg.market,
                    last_price,
                    current_position,
                    target_position,
                    f"dry_run_{side}",
                    decision_reason,
                )
                print(
                    f"[LIVE][DRY_RUN] {symbol} would {side} qty={abs(delta)} "
                    f"price={last_price:.2f} reason={decision_reason}"
                )
                continue

            broker.submit_market_order(symbol=symbol, qty=abs(delta), side=side)
            _append_trade_log(
                symbol,
                cfg.market,
                last_price,
                current_position,
                target_position,
                side,
                decision_reason,
            )
            print(
                f"[LIVE] {symbol} price={last_price:.2f} "
                f"pos={current_position}->{target_position} action={side} qty={abs(delta)} "
                f"reason={decision_reason}"
            )
    finally:
        broker.close()


def is_market_open_now(market: str) -> bool:
    market = market.upper()
    if market == "US":
        now_et = datetime.now(tz=ZoneInfo("America/New_York"))
        if now_et.weekday() >= 5:
            return False
        hm = now_et.hour * 100 + now_et.minute
        return 930 <= hm <= 1600

    if market == "HK":
        now_hk = datetime.now(tz=ZoneInfo("Asia/Hong_Kong"))
        if now_hk.weekday() >= 5:
            return False
        hm = now_hk.hour * 100 + now_hk.minute
        in_morning = 930 <= hm <= 1200
        in_afternoon = 1300 <= hm <= 1600
        return in_morning or in_afternoon

    return False


def _is_market_open(cfg: AppConfig, broker: BaseBroker) -> bool:
    if cfg.market == "US":
        # Alpaca clock handles weekends and exchange holidays.
        return broker.is_market_open_now()
    return is_market_open_now(cfg.market)


def _risk_exit_reason(
    current_position: int,
    avg_entry_price: float,
    last_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> str:
    """Return stop-loss/take-profit reason, empty string means no forced exit."""
    if current_position <= 0 or avg_entry_price <= 0:
        return ""
    pnl_pct = last_price / avg_entry_price - 1.0
    if pnl_pct <= -abs(stop_loss_pct):
        return "stop_loss_triggered"
    if pnl_pct >= abs(take_profit_pct):
        return "take_profit_triggered"
    return ""


def _market_date_str(market: str) -> str:
    if market.upper() == "US":
        return datetime.now(tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    if market.upper() == "HK":
        return datetime.now(tz=ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d")
    return datetime.utcnow().strftime("%Y-%m-%d")


def _daily_risk_state_path() -> Path:
    return Path("logs") / "daily_risk_state.json"


def _load_daily_risk_state() -> dict:
    path = _daily_risk_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_daily_risk_state(state: dict) -> None:
    path = _daily_risk_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _is_daily_loss_circuit_breaker_triggered(cfg: AppConfig, broker: BaseBroker) -> bool:
    """Track start-of-day equity and trigger breaker on excessive daily drawdown."""
    if cfg.max_daily_loss_pct <= 0:
        return False
    equity = broker.get_account_equity()
    market_date = _market_date_str(cfg.market)
    state = _load_daily_risk_state()

    if state.get("market_date") != market_date:
        state = {"market_date": market_date, "start_equity": equity}
        _save_daily_risk_state(state)
        return False

    start_equity = float(state.get("start_equity", equity))
    if start_equity <= 0:
        return False
    daily_return = equity / start_equity - 1.0
    return daily_return <= -abs(cfg.max_daily_loss_pct)


def run_live_with_retries(cfg: AppConfig) -> None:
    attempts = max(1, cfg.live_max_retries)
    for attempt in range(1, attempts + 1):
        try:
            run_live_cycle(cfg)
            return
        except Exception as exc:
            msg = f"[LIVE][ERROR] attempt={attempt}/{attempts} error={exc}"
            print(msg)
            send_webhook_alert(cfg.alert_webhook_url, msg)
            if attempt == attempts:
                raise
