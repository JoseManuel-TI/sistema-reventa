import logging
import urllib.request
import urllib.error
import json

import config

_API = "https://api.telegram.org/bot{token}/sendMessage"


def telegram(mensaje):
    token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    payload = json.dumps({
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()

    req = urllib.request.Request(
        _API.format(token=token),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logging.error("Telegram notification failed: %s", e)
        return False
