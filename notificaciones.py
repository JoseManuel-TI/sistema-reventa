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


def _fmt_pesos(valor):
    try:
        return f"$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "$ 0,00"


def pedido_nuevo(pedido, items):
    lineas = "\n".join(
        f"  • {i['nombre']} x{i['cantidad']} = {_fmt_pesos(i['subtotal'])}"
        for i in items
    )
    telefono = pedido.get("cliente_telefono") or "—"
    direccion = pedido.get("cliente_direccion") or "—"
    mensaje = (
        f"🛒 <b>Pedido nuevo #{pedido['id']}</b>\n\n"
        f"👤 {pedido['cliente_nombre']}\n"
        f"📧 {pedido['cliente_email']}\n"
        f"📱 {telefono}\n"
        f"🏠 {direccion}\n\n"
        f"{lineas}\n\n"
        f"<b>Total: {_fmt_pesos(pedido['total'])}</b>\n"
        f"Estado: pendiente de confirmación"
    )
    return telegram(mensaje)
