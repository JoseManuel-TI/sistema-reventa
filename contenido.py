"""
Gestión de contenido para redes sociales.
Scheduler, cola de publicaciones, posteo a Telegram.
"""

import os
import random
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

PAUSA_ENTRE_POSTEOS = 3

BASE_DIR = os.path.dirname(__file__)

import config
import db as app_db
import instagram_api
import integraciones as itgr
import marketing
import notificaciones

# Usamos el mismo DATA_DIR que db.py para que el schedule viva en el volumen
# persistente (/data en Railway) y no se pierda en cada deploy.
DATA_DIR = app_db.DATA_DIR
SCHEDULE_DB = os.path.join(DATA_DIR, "contenido.db")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _ruta_imagen_local(archivo):
    """Resuelve la ruta física de una imagen de producto.

    `archivo` viene como ruta web ('imagenes/proveedores/...'); la convertimos
    a la ruta real dentro de `db.imagenes_dir()` (que apunta al volumen en prod).
    Devuelve None si es una URL externa.
    """
    if not archivo or archivo.startswith(("http://", "https://")):
        return None
    rel = archivo[len("imagenes/"):] if archivo.startswith("imagenes/") else archivo
    return os.path.join(app_db.imagenes_dir(), rel)


def _tracking_url(producto, origen):
    url_ext = itgr.producto_url_externa(producto)
    if not url_ext:
        return None
    base_url = (config.get("PUBLIC_URL") or "https://clickya.net").rstrip("/")
    return f"{base_url}/out/{producto['id']}?src={origen}"


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
    url_ext = _tracking_url(producto, "telegram") or itgr.producto_url_externa(producto)

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
    precio = f"$ {pv:,.0f}".replace(",", ".")
    wa = config.whatsapp()
    wa_link = f"{wa}?text=Hola%2C+quiero+{nombre.replace(' ', '%20')}"
    public_url = (config.get("PUBLIC_URL") or "https://clickya.net").rstrip("/")
    producto_url = f"{public_url}/tienda/{producto['id']}"

    beneficios = marketing.lineas_beneficios(producto)
    bloque_benef = "".join(f"✅ {b}\n" for b in beneficios)
    if bloque_benef:
        bloque_benef += "\n"

    caption = (
        f"🛒 <b>{nombre}</b>\n\n"
        f"{desc}\n\n"
        f"{bloque_benef}"
        f"💰 <b>Precio:</b> {precio}\n"
        f"🚚 {marketing.ENVIO_TEXTO}\n\n"
        f"📲 <a href='{wa_link}'>Comprar por WhatsApp</a>\n"
        f"🔗 <a href='{producto_url}'>Ver en la tienda</a>\n\n"
        f"{marketing.hashtags_producto(producto, extra=['oferta'], limite=10)}"
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

    img_path = _ruta_imagen_local(imgs[0]["archivo"])
    if not img_path or not os.path.exists(img_path):
        return False, f"Imagen no encontrada: {imgs[0]['archivo']}"

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


def _hay_categoria_pendiente(conn, fecha, categoria):
    cat = (categoria or "").strip().lower()
    filas = conn.execute(
        "SELECT producto_id FROM publicaciones "
        "WHERE estado='pendiente' AND date(programada_para)=?",
        (fecha,),
    ).fetchall()
    for (pid,) in filas:
        prod = app_db.get_producto(pid)
        if prod and (prod.get("categoria") or "").strip().lower() == cat:
            return True
    return False


def programar_dos_diarias(
    dias=14,
    por_dia=2,
    categoria_destacada="Perfumes",
    incluir_externos=False,
):
    """Asegura `por_dia` publicaciones por día desde mañana.

    Reserva un lugar diario para `categoria_destacada` (ej. perfumes) y
    completa el resto con el catálogo general. Es idempotente por fecha.
    """
    _init_db()
    publicables = [
        p for p in app_db.get_productos(publicado_only=True)
        if _producto_publicable(p, incluir_externos=incluir_externos)
    ]
    cat = (categoria_destacada or "").strip().lower()
    destacados = [p for p in publicables if (p.get("categoria") or "").strip().lower() == cat]
    normales = [p for p in publicables if (p.get("categoria") or "").strip().lower() != cat]
    destacados.sort(key=_score_producto, reverse=True)
    normales.sort(key=_score_producto, reverse=True)

    conn = _get_conn()
    creadas = []
    now = datetime.now()
    try:
        usados = _productos_ya_programados(conn)
        cola_dest = [p for p in destacados if p["id"] not in usados] or destacados
        cola_norm = [p for p in normales if p["id"] not in usados] or normales

        for offset in range(dias):
            fecha = (now + timedelta(days=offset + 1)).strftime("%Y-%m-%d")
            existentes = conn.execute(
                "SELECT COUNT(*) FROM publicaciones "
                "WHERE estado='pendiente' AND date(programada_para)=?",
                (fecha,),
            ).fetchone()[0]
            if existentes >= por_dia:
                continue

            if not cola_dest:
                cola_dest = list(destacados)
            if not cola_norm:
                cola_norm = list(normales)

            if cola_dest and not _hay_categoria_pendiente(conn, fecha, categoria_destacada):
                producto = cola_dest.pop(0)
                conn.execute(
                    "INSERT INTO publicaciones (producto_id, programada_para, caption) VALUES (?,?,?)",
                    (producto["id"], fecha, generar_caption(producto)),
                )
                creadas.append({"producto_id": producto["id"], "producto": producto["nombre"], "fecha": fecha})
                existentes += 1

            while existentes < por_dia and cola_norm:
                producto = cola_norm.pop(0)
                conn.execute(
                    "INSERT INTO publicaciones (producto_id, programada_para, caption) VALUES (?,?,?)",
                    (producto["id"], fecha, generar_caption(producto)),
                )
                creadas.append({"producto_id": producto["id"], "producto": producto["nombre"], "fecha": fecha})
                existentes += 1
        conn.commit()
    finally:
        conn.close()
    return creadas


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
                time.sleep(PAUSA_ENTRE_POSTEOS)
        conn.commit()
        return result
    finally:
        conn.close()


def productos_sin_instagram(limite=10):
    """Productos publicados que no tienen un posteo exitoso en Instagram.

    Un posteo exitoso guarda en `contenido_log` el media_id (numérico); los
    errores guardan texto. Por eso se distinguen con GLOB.
    """
    _init_db()
    conn = _get_conn()
    try:
        filas = conn.execute(
            "SELECT p.producto_id, MAX(p.publicada_en) AS cuando "
            "FROM publicaciones p "
            "WHERE p.estado='publicado' "
            "AND p.producto_id NOT IN ("
            "  SELECT producto_id FROM contenido_log "
            "  WHERE canal='instagram' AND resultado GLOB '[0-9]*'"
            ") "
            "GROUP BY p.producto_id "
            "ORDER BY cuando DESC LIMIT ?",
            (int(limite),),
        ).fetchall()
        return [f[0] for f in filas]
    finally:
        conn.close()


def republicar_instagram(limite=10, base_url="https://clickya.net"):
    """Reenvía a Instagram los publicados que sólo salieron por Telegram.

    Devuelve (ok, fallidos, detalle) con detalle = [(producto_id, mensaje)].
    """
    if not instagram_api.configurado():
        return 0, 0, [("", "Instagram no configurado")]

    ids = productos_sin_instagram(limite=limite)
    ok_count, fallidos, detalle = 0, 0, []
    conn = _get_conn()
    try:
        for pid in ids:
            ok, msg = instagram_api.postear_producto(pid, base_url)
            conn.execute(
                "INSERT INTO contenido_log (producto_id, canal, resultado) "
                "VALUES (?, 'instagram', ?)",
                (pid, msg),
            )
            if ok:
                ok_count += 1
            else:
                fallidos += 1
            detalle.append((pid, msg))
            if ok:
                time.sleep(PAUSA_ENTRE_POSTEOS)
        conn.commit()
    finally:
        conn.close()
    return ok_count, fallidos, detalle


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
