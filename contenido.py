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
DATA_DIR = os.environ.get("APP_DATA_DIR")
if not DATA_DIR and os.environ.get("RAILWAY_ENVIRONMENT"):
    DATA_DIR = "/data"
DATA_DIR = DATA_DIR or os.path.join(BASE_DIR, "data")
SCHEDULE_DB = os.path.join(DATA_DIR, "contenido.db")

import db as app_db
import config
import instagram_api
import integraciones as itgr
import notificaciones

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
    tipo = producto.get("tipo_producto")
    es_externo = itgr.es_externo(tipo) or bool(producto.get("es_afiliado"))
    url_ext = itgr.producto_url_externa(producto)

    if es_externo:
        plataforma = producto.get("plataforma_afiliado") or itgr.detectar_plataforma(url_ext or "")
        if tipo == "afiliado_digital" and plataforma == "hotmart":
            cta = f"🎓 <a href='{url_ext}'>Acceder al curso</a>"
            tag = "#CursoOnline #Formacion"
        elif plataforma == "aliexpress":
            cta = f"🛒 <a href='{url_ext}'>Ver precio en AliExpress</a>"
            tag = "#AliExpress #Importado"
        elif plataforma == "mercadolibre":
            cta = f"🛒 <a href='{url_ext}'>Ver oferta en Mercado Libre</a>"
            tag = "#MercadoLibre #Oferta"
        else:
            cta = f"🛒 <a href='{url_ext}'>Ver precio en Amazon</a>"
            tag = "#Amazon #Importado"
        caption = (
            f"🛒 <b>{nombre}</b>\n\n"
            f"{desc}\n\n"
            f"{cta}\n\n"
            f"✅ Compra 100% segura con garantía de la plataforma\n\n"
            f"{tag} #ClickYa"
        )
        return caption

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
        ok = notificaciones.telegram(caption)
        return ok, "OK texto sin imagen" if ok else "Producto sin imagen y Telegram texto falló"

    img_path = os.path.join(BASE_DIR, imgs[0]["archivo"])
    if not os.path.exists(img_path):
        ok = notificaciones.telegram(caption)
        return ok, "OK texto sin imagen local" if ok else f"Imagen no encontrada: {img_path}"

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
            with urllib.request.urlopen(req, timeout=12) as resp:
                result = resp.status == 200
                msg = "OK" if result else f"HTTP {resp.status}"
                return result, msg
    except Exception as e:
        ok = notificaciones.telegram(caption)
        return ok, f"OK texto fallback; foto falló: {e}" if ok else str(e)


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
    productos = [p for p in productos
                 if itgr.es_externo(p.get("tipo_producto")) or p.get("es_afiliado")
                 or (p.get("precio_venta") and p["precio_venta"] > 0)]
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


def registrar_publicacion_manual(producto_id, caption=None, resultado="OK manual"):
    """Guarda una publicacion ejecutada fuera de la cola programada."""
    _init_db()
    if not caption:
        producto = app_db.get_producto(producto_id)
        caption = generar_caption(producto) if producto else ""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO publicaciones
                (producto_id, caption, estado, programada_para, publicada_en)
            VALUES (?, ?, 'publicado', date('now'), datetime('now','localtime'))
            """,
            (producto_id, caption),
        )
        conn.execute(
            "INSERT INTO contenido_log (producto_id, canal, resultado) VALUES (?, 'manual', ?)",
            (producto_id, resultado),
        )
        conn.commit()
    finally:
        conn.close()


def cancelar_atrasadas():
    """Cancela pendientes anteriores a hoy para evitar backlog obsoleto."""
    _init_db()
    conn = _get_conn()
    try:
        cur = conn.execute(
            """
            UPDATE publicaciones
            SET estado='cancelado'
            WHERE estado='pendiente'
              AND programada_para IS NOT NULL
              AND date(programada_para) < date('now')
            """
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def reprogramar_atrasadas(desde=None, cantidad_diaria=1):
    """Mueve pendientes vencidas a fechas libres desde hoy o desde la fecha indicada."""
    _init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id FROM publicaciones
            WHERE estado='pendiente'
              AND programada_para IS NOT NULL
              AND date(programada_para) < date('now')
            ORDER BY programada_para ASC, id ASC
            """
        ).fetchall()
        if not rows:
            return []

        inicio = datetime.strptime(desde, "%Y-%m-%d") if desde else datetime.now()
        ocupadas = _fechas_pendientes(conn)
        movidas = []
        fecha = inicio
        usadas_en_fecha = 0
        for row in rows:
            while fecha.strftime("%Y-%m-%d") in ocupadas or usadas_en_fecha >= cantidad_diaria:
                fecha += timedelta(days=1)
                usadas_en_fecha = 0
            nueva_fecha = fecha.strftime("%Y-%m-%d")
            conn.execute(
                "UPDATE publicaciones SET programada_para=? WHERE id=?",
                (nueva_fecha, row[0]),
            )
            movidas.append({"id": row[0], "fecha": nueva_fecha})
            usadas_en_fecha += 1
        conn.commit()
        return movidas
    finally:
        conn.close()


def _producto_publicable(producto, incluir_externos=False):
    es_externo = itgr.es_externo(producto.get("tipo_producto")) or bool(producto.get("es_afiliado"))
    if es_externo:
        return incluir_externos
    return bool(
        producto.get("publicar")
        and producto.get("activo", 1)
        and (producto.get("stock") or 0) > 0
        and (producto.get("precio_venta") or 0) > 0
    )


def _score_producto(producto):
    nombre = (producto.get("nombre") or "").lower()
    categoria = (producto.get("categoria") or "").lower()
    score = 0
    for palabra in ("redmi", "xiaomi", "smartwatch", "freidora", "airpods", "auriculares", "cargador"):
        if palabra in nombre:
            score += 25
    if categoria in ("celulares", "audio", "hogar", "accesorios"):
        score += 10
    score += min(int(producto.get("stock") or 0), 5)
    precio = producto.get("precio_venta") or 0
    if precio and precio <= 400000:
        score += 8
    return score


def _fechas_pendientes(conn):
    rows = conn.execute(
        "SELECT DISTINCT date(programada_para) FROM publicaciones WHERE estado='pendiente'"
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def _productos_ya_programados(conn):
    rows = conn.execute(
        "SELECT DISTINCT producto_id FROM publicaciones WHERE estado IN ('pendiente', 'publicado')"
    ).fetchall()
    return {r[0] for r in rows}


def programar_automatico(dias=7, cantidad_diaria=1, incluir_externos=False):
    """Completa la cola de publicaciones con productos de venta directa.

    Prioriza productos locales con stock, precio y categorías de mayor intención
    para el arranque comercial. Es idempotente por fecha y producto.
    """
    _init_db()
    productos = [
        p for p in app_db.get_productos(publicado_only=True)
        if _producto_publicable(p, incluir_externos=incluir_externos)
    ]
    productos.sort(key=_score_producto, reverse=True)

    conn = _get_conn()
    creadas = []
    try:
        fechas_ocupadas = _fechas_pendientes(conn)
        usados = _productos_ya_programados(conn)
        candidatos = [p for p in productos if p["id"] not in usados] or productos
        now = datetime.now()

        for offset in range(dias):
            fecha = (now + timedelta(days=offset)).strftime("%Y-%m-%d")
            if fecha in fechas_ocupadas:
                continue
            for _ in range(cantidad_diaria):
                if not candidatos:
                    break
                producto = candidatos.pop(0)
                conn.execute(
                    "INSERT INTO publicaciones (producto_id, programada_para, caption) VALUES (?,?,?)",
                    (producto["id"], fecha, generar_caption(producto)),
                )
                creadas.append({"producto_id": producto["id"], "producto": producto["nombre"], "fecha": fecha})
        conn.commit()
    finally:
        conn.close()
    return creadas


def publicar_pendientes(base_url="http://localhost:5000", limite=None, incluir_atrasadas=True):
    _init_db()
    conn = _get_conn()
    try:
        operador_fecha = "<=" if incluir_atrasadas else "="
        query = (
            "SELECT p.id, p.producto_id, p.caption FROM publicaciones p "
            f"WHERE p.estado='pendiente' AND date(p.programada_para) {operador_fecha} date('now') "
            "ORDER BY p.programada_para ASC"
        )
        params = []
        if limite:
            query += " LIMIT ?"
            params.append(int(limite))
        pendientes = conn.execute(query, params).fetchall()

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


def resumen_cola():
    _init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) AS pendientes,
                SUM(CASE WHEN estado='publicado' THEN 1 ELSE 0 END) AS publicados,
                SUM(CASE WHEN estado='error' THEN 1 ELSE 0 END) AS errores,
                SUM(CASE
                    WHEN estado='pendiente'
                     AND programada_para IS NOT NULL
                     AND date(programada_para) < date('now')
                    THEN 1 ELSE 0
                END) AS atrasadas
            FROM publicaciones
            """
        ).fetchone()
        return {
            "total": row[0] or 0,
            "pendientes": row[1] or 0,
            "publicados": row[2] or 0,
            "errores": row[3] or 0,
            "atrasadas": row[4] or 0,
        }
    finally:
        conn.close()


def proxima_publicacion():
    _init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT producto_id, programada_para
            FROM publicaciones
            WHERE estado='pendiente' AND programada_para IS NOT NULL
            ORDER BY programada_para ASC
            LIMIT 1
            """
        ).fetchone()
        return {"producto_id": row[0], "fecha": row[1]} if row else None
    finally:
        conn.close()


def diagnostico_comercial():
    productos = app_db.get_productos(publicado_only=True)
    locales = [p for p in productos if not itgr.es_externo(p.get("tipo_producto")) and not p.get("es_afiliado")]
    sin_stock = [p for p in locales if (p.get("stock") or 0) <= 0]
    sin_precio = [p for p in locales if (p.get("precio_venta") or 0) <= 0]
    sin_imagen = [p for p in locales if not app_db.get_imagenes(p["id"])]
    publicables = [p for p in locales if _producto_publicable(p)]
    top = sorted(publicables, key=_score_producto, reverse=True)[:5]
    return {
        "productos_publicados": len(productos),
        "locales_publicables": len(publicables),
        "sin_stock": len(sin_stock),
        "sin_precio": len(sin_precio),
        "sin_imagen": len(sin_imagen),
        "top": [{"id": p["id"], "nombre": p["nombre"], "stock": p.get("stock") or 0} for p in top],
    }


def rutina_diaria(base_url="https://clickya.net", dias_programados=7):
    """Rutina diaria: rellena calendario, publica pendientes y emite resumen."""
    nuevas = programar_automatico(dias=dias_programados)
    publicados = publicar_pendientes(base_url=base_url, limite=1, incluir_atrasadas=False)
    pubs = listar_publicaciones(limit=100)
    pendientes = sum(1 for p in pubs if p["estado"] == "pendiente")
    errores = sum(1 for p in pubs if p["estado"] == "error")
    diag = diagnostico_comercial()
    proxima = proxima_publicacion()

    ok_publicados = sum(1 for _, ok, _ in publicados if ok)
    err_publicados = sum(1 for _, ok, _ in publicados if not ok)
    top = "\n".join(
        f"  • #{p['id']} {p['nombre'][:45]} (stock {p['stock']})"
        for p in diag["top"]
    ) or "  • Sin productos publicables"
    mensaje = (
        f"🤖 <b>Rutina diaria ClickYa</b>\n\n"
        f"Programadas nuevas: {len(nuevas)}\n"
        f"Publicadas hoy: {ok_publicados}\n"
        f"Errores de publicación: {err_publicados}\n"
        f"Pendientes en cola: {pendientes}\n"
        f"Errores acumulados: {errores}\n\n"
        f"Productos locales publicables: {diag['locales_publicables']}\n"
        f"Sin stock: {diag['sin_stock']} · Sin precio: {diag['sin_precio']} · Sin imagen: {diag['sin_imagen']}\n\n"
        f"<b>Prioridad comercial</b>\n{top}"
    )
    if proxima:
        mensaje += f"\n\nPróxima publicación: producto #{proxima['producto_id']} el {proxima['fecha']}"

    notificado = notificaciones.telegram(mensaje)
    return {
        "programadas": nuevas,
        "publicaciones": publicados,
        "pendientes": pendientes,
        "errores": errores,
        "diagnostico": diag,
        "proxima": proxima,
        "telegram": notificado,
    }
