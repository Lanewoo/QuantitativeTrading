"""
简单告警：向 Webhook POST JSON（如企业微信/飞书机器人兼容 text 字段时可用）。
"""

from __future__ import annotations

import requests


def send_webhook_alert(webhook_url: str, message: str) -> None:
    """url 为空则不发请求。"""

    if not webhook_url:
        return
    requests.post(
        webhook_url,
        json={"text": message},
        timeout=10,
    )
