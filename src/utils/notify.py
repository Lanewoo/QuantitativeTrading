from __future__ import annotations

import requests


def send_webhook_alert(webhook_url: str, message: str) -> None:
    if not webhook_url:
        return
    requests.post(
        webhook_url,
        json={"text": message},
        timeout=10,
    )
