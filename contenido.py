"""
Gestión de contenido para redes sociales.
Scheduler, cola de publicaciones, posteo a Telegram.
"""

import json
import logging
import os
import random
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
SCHEDULE_DB = os.path.join(DATA_DIR, "contenido.db")

import db as app_db
import config
import instagram_api

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(SCHEDULE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS publicaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            caption TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            programada_para TEXT,
            publicada_en TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contenido_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            canal TEXT NOT NULL,
            resultado TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()
    return True


def _get_conn():
    return sqlite3.connect(SCHEDULE_DB)


# ─── Generar caption ────────────────────────────────────────────────

def generar_caption(producto):
    nombre = producto["nombre"]
    desc = (producto.get("descripcion") or "")[:200]
    pv = producto.get("precio_venta") or 0
    precio = f"$ {pv:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    wa = config.get("TIENDA_WA") or "https://wa.me/5491126268359"
    wa_link = f"{wa}?text=Hola%2C+quiero+{nombre.replace(' ', '%20')}"

    caption = (
        f"🛒 <b>{nombre}</b>\n\n"
        f"{desc}\n\n"
        f"💰 <b>Precio:</b> {precio}\n"
        f"🚚 Envío gratis - 24 hs hábiles\n\n"
        f"📲 <a href='{wa_link}'>Comprar por WhatsApp</a>\n\n"
        f"#ClickYa #Oferta #EnvioGratis"
    )
    return caption


# ─── Postear a Telegram ─────────────────────────────────────────────

def postear_telegram(producto, caption=None):
    token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados"

    if not caption:
        caption = generar_caption(producto)

    imgs = app_db.get_imagenes(producto["id"])
    if not imgs:
        return False, "Producto sin imagen"

    img_path = os.path.join(BASE_DIR, imgs[0]["archivo"])
    if not os.path.exists(img_path):
        return False, f"Imagen no encontrada: {img_path}"

    try:
        with open(img_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            import uuid
            boundary = "----" + uuid.uuid4().hex
            body = _encode_multipart(data, files, boundary)

            req = urllib.request.Request(
                _TELEGRAM_API.format(token=token, method="sendPhoto"),
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.status == 200
                msg = "OK" if result else f"HTTP {resp.status}"
                return result, msg
    except Exception as e:
        return False, str(e)


def _encode_multipart(data, files, boundary):
    body = b""
    for key, value in data.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()
    for key, fileobj in files.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"; filename="{getattr(fileobj, "name", "photo.jpg")}"\r\n'.encode()
        body += b"Content-Type: image/jpeg\r\n\r\n"
        body += fileobj.read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body


# ─── Programar publicaciones ────────────────────────────────────────

def programar_publicacion(producto_id, fecha=None):
    _init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO publicaciones (producto_id, programada_para) VALUES (?, ?)",
            (producto_id, fecha),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def programar_todos(fecha_inicio=None):
    _init_db()
    productos = app_db.get_productos(publicado_only=True)
    productos = [p for p in productos if p.get("precio_venta") and p["precio_venta"] > 0]
    random.shuffle(productos)

    conn = _get_conn()
    now = datetime.now()
    count = 0
    try:
        for i, p in enumerate(productos):
            fecha = (now + timedelta(days=i)).strftime("%Y-%m-%d") if not fecha_inicio else (
                datetime.strptime(fecha_inicio, "%Y-%m-%d") + timedelta(days=i)
            ).strftime("%Y-%m-%d")
            existing = conn.execute(
                "SELECT id FROM publicaciones WHERE producto_id=? AND date(programada_para)=?",
                (p["id"], fecha),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO publicaciones (producto_id, programada_para, caption) VALUES (?,?,?)",
                    (p["id"], fecha, generar_caption(p)),
                )
                count += 1
        conn.commit()
    finally:
        conn.close()
    return count


def publicar_pendientes(base_url="http://localhost:5000"):
    _init_db()
    conn = _get_conn()
    try:
        pendientes = conn.execute(
            "SELECT p.id, p.producto_id, p.caption FROM publicaciones p WHERE p.estado='pendiente' AND date(p.programada_para) <= date('now') ORDER BY p.programada_para ASC"
        ).fetchall()

        result = []
        for pub_id, prod_id, caption in pendientes:
            producto = app_db.get_producto(prod_id)
            if not producto:
                conn.execute("UPDATE publicaciones SET estado='cancelado' WHERE id=?", (pub_id,))
                continue

            # Telegram
            ok_tg, msg_tg = postear_telegram(producto, caption)
            conn.execute(
                "INSERT INTO contenido_log (producto_id, canal, resultado) VALUES (?, 'telegram', ?)",
                (prod_id, msg_tg),
            )

            # Instagram (si está configurado)
            ok_ig = False
            msg_ig = ""
            if instagram_api.configurado():
                ok_ig, msg_ig = instagram_api.postear_producto(prod_id, base_url)
                conn.execute(
                    "INSERT INTO contenido_log (producto_id, canal, resultado) VALUES (?, 'instagram', ?)",
                    (prod_id, msg_ig),
                )

            ok = ok_tg or ok_ig
            conn.execute(
                "UPDATE publicaciones SET estado=?, publicada_en=datetime('now','localtime') WHERE id=?",
                ("publicado" if ok else "error", pub_id),
            )
            result.append((prod_id, ok, f"TG:{msg_tg} | IG:{msg_ig}"))
            if ok:
                import time
                time.sleep(3)
        conn.commit()
        return result
    finally:
        conn.close()


def listar_publicaciones(limit=20):
    _init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, producto_id, estado, programada_para, publicada_en FROM publicaciones ORDER BY programada_para DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            prod = app_db.get_producto(r[1])
            result.append({
                "id": r[0],
                "producto_id": r[1],
                "producto_nombre": prod["nombre"] if prod else None,
                "estado": r[2],
                "programada_para": r[3],
                "publicada_en": r[4],
            })
        return result
    finally:
        conn.close()


def proxima_publicacion():
    _init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT producto_id, programada_para FROM publicaciones WHERE estado='pendiente' ORDER BY programada_para ASC LIMIT 1"
        ).fetchone()
        return {"producto_id": row[0], "fecha": row[1]} if row else None
    finally:
        conn.close()
