"""
APP_MODE=live_loop 时使用：无限循环，每隔 LIVE_INTERVAL_MINUTES 执行一轮 live。
"""

from __future__ import annotations

import time

from datetime import datetime

from config import AppConfig
from engine.live import run_live_with_retries
from utils.notify import send_webhook_alert


def run_live_scheduler(cfg: AppConfig) -> None:
    """阻塞运行直到进程被杀死；单轮异常会告警并继续下一轮睡眠。"""
    interval_seconds = max(1, cfg.live_interval_minutes) * 60

    print(f"[SCHEDULER] started interval={cfg.live_interval_minutes}m")
    while True:
        try:
            run_live_with_retries(cfg)
        except Exception as exc:
            msg = f"[SCHEDULER][ERROR] ts={datetime.utcnow().isoformat()} error={exc}"
            print(msg)
            send_webhook_alert(cfg.alert_webhook_url, msg)
        time.sleep(interval_seconds)
