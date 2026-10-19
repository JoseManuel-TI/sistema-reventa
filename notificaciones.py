import json
import logging
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

import config

_API = "https://api.telegram.org/bot{token}/sendMessage"
_API_DOC = "https://api.telegram.org/bot{token}/sendDocument"


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


def telegram_documento(path, caption=""):
    """Envía un archivo (p. ej. el ZIP de respaldo) por Telegram."""
    token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    if not os.path.exists(path):
        logging.error("telegram_documento: no existe %s", path)
        return False

    with open(path, "rb") as f:
        contenido = f.read()

    nombre = os.path.basename(path)
    tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    boundary = "----clickya" + uuid.uuid4().hex
    cuerpo = _multipart(
        boundary,
        [("chat_id", chat_id), ("caption", caption)],
        nombre, tipo, contenido,
    )
    return _enviar_documento(token, cuerpo, boundary)


def _multipart(boundary, campos, nombre, tipo, contenido):
    lineas = []
    for clave, valor in campos:
        if valor:
            lineas.append(f"--{boundary}\r\n")
            lineas.append(f'Content-Disposition: form-data; name="{clave}"\r\n\r\n')
            lineas.append(f"{valor}\r\n")
    lineas.append(f"--{boundary}\r\n")
    lineas.append(f'Content-Disposition: form-data; name="document"; filename="{nombre}"\r\n')
    lineas.append(f"Content-Type: {tipo}\r\n\r\n")
    cabecera = "".join(lineas).encode()
    return cabecera + contenido + f"\r\n--{boundary}--\r\n".encode()


def _enviar_documento(token, cuerpo, boundary):
    req = urllib.request.Request(
        _API_DOC.format(token=token),
        data=cuerpo,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(cuerpo)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logging.error("Telegram documento falló: %s", e)
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
