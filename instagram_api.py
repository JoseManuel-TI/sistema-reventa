"""
Publicación automática en Instagram via Graph API.
Requiere: Meta App + Token de página de Facebook con permisos de Instagram.

Guía de setup:
1. Crear app en https://developers.facebook.com (tipo Business)
2. Agregar producto "Instagram Graph API"
3. Generar token con permisos: instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement
4. Vincular cuenta de Instagram Business/Creator a una página de Facebook
5. Obtener IG Business ID desde Graph Explorer (GET /me/accounts → page_id → GET /{page_id}?fields=instagram_business_account)
6. Configurar en data/config.json o env vars:
   - FB_PAGE_TOKEN: token de acceso de página
   - FB_PAGE_ID: ID de la página de Facebook
   - IG_BUSINESS_ID: ID de la cuenta de Instagram Business
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import db
import integraciones as itgr
import marketing
import reels

GRAPH_API = "https://graph.facebook.com/v22.0"


class InstagramError(Exception):
    pass


def _get_config():
    token = config.get("FB_PAGE_TOKEN")
    ig_id = config.get("IG_BUSINESS_ID")
    return token, ig_id


def configurado():
    token, ig_id = _get_config()
    return bool(token and ig_id)


def _colaboradores():
    """Usernames de IG para Collab posts (env `IG_COLLABORATORS`, separados por coma)."""
    raw = config.get("IG_COLLABORATORS") or ""
    return [u.strip().lstrip("@") for u in str(raw).split(",") if u.strip()]


def _api_call(method, endpoint, data=None, params=None):
    token, _ = _get_config()
    if not token:
        raise InstagramError("FB_PAGE_TOKEN no configurado")

    url = f"{GRAPH_API}/{endpoint}"
    if params:
        params["access_token"] = token
    else:
        params = {"access_token": token}

    url += "?" + urllib.parse.urlencode(params)

    if data:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method=method)
    else:
        req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise InstagramError(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise InstagramError(f"Error de conexión: {e.reason}") from e


def postear_foto(imagen_url, caption):
    """
    Publica una foto en Instagram.
    Retorna (success: bool, media_id_or_error: str)
    """
    token, ig_id = _get_config()
    if not token or not ig_id:
        return False, "Instagram no configurado (FB_PAGE_TOKEN / IG_BUSINESS_ID)"

    if not imagen_url.startswith("http"):
        return False, "La imagen debe ser accesible via URL pública (https)"

    try:
        # Paso 1: Crear container de media
        data = {
            "image_url": imagen_url,
            "caption": caption[:2200],
        }
        colabs = _colaboradores()
        if colabs:
            data["collaborators"] = colabs
        result = _api_call("POST", f"{ig_id}/media", data=data)
        creation_id = result.get("id")
        if not creation_id:
            return False, f"No se obtuvo creation_id: {result}"

        # Esperar a que se procese
        time.sleep(3)

        # Paso 2: Publicar
        publish = _api_call("POST", f"{ig_id}/media_publish", data={"creation_id": creation_id})
        media_id = publish.get("id")
        if not media_id:
            return False, f"No se obtuvo media_id: {publish}"

        return True, media_id

    except InstagramError as e:
        return False, str(e)


def esperar_video(creation_id, intentos=40, espera=3):
    """Espera a que Meta termine de procesar el video del reel."""
    for _ in range(intentos):
        estado = _api_call("GET", creation_id, params={"fields": "status_code,status"})
        codigo = estado.get("status_code")
        if codigo == "FINISHED":
            return True, "FINISHED"
        if codigo in ("ERROR", "EXPIRED"):
            return False, estado.get("status") or codigo
        time.sleep(espera)
    return False, "Timeout esperando el procesamiento del video"


def postear_reel(producto, caption, base_url):
    """Publica un Reel 9:16 generado desde la foto del producto."""
    ok, video_url = reels.generar_reel(producto, base_url)
    if not ok:
        return False, video_url

    _, ig_id = _get_config()
    try:
        data = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true",
        }
        colabs = _colaboradores()
        if colabs:
            data["collaborators"] = colabs
        result = _api_call("POST", f"{ig_id}/media", data=data)
        creation_id = result.get("id")
        if not creation_id:
            return False, f"No se obtuvo creation_id: {result}"

        ok_video, detalle = esperar_video(creation_id)
        if not ok_video:
            return False, f"Video no procesado: {detalle}"

        publish = _api_call("POST", f"{ig_id}/media_publish", data={"creation_id": creation_id})
        media_id = publish.get("id")
        if not media_id:
            return False, f"No se obtuvo media_id: {publish}"
        return True, media_id
    except InstagramError as e:
        return False, str(e)


def _es_externo(producto):
    tipo = producto.get("tipo_producto")
    return bool(producto.get("es_afiliado")) or tipo in ("amazon_affiliate", "afiliado_digital")


def construir_caption(producto):
    """Arma el texto del posteo de Instagram (gancho, beneficios, CTA, hashtags)."""
    nombre = producto["nombre"]
    public_url = (config.get("PUBLIC_URL") or "https://clickya.net").rstrip("/")
    bio_url = public_url.replace("https://", "")

    beneficios = marketing.lineas_beneficios(producto)
    bloque_benef = "".join(f"✅ {b}\n" for b in beneficios)
    if bloque_benef:
        bloque_benef += "\n"

    if _es_externo(producto):
        url = itgr.producto_url_externa(producto) or ""
        plataforma = producto.get("plataforma_afiliado") or itgr.detectar_plataforma(url)
        destino = {
            "hotmart": "Hotmart",
            "aliexpress": "AliExpress",
            "mercadolibre": "Mercado Libre",
        }.get(plataforma, "Amazon")
        return (
            f"🛒 {nombre}\n\n"
            f"{bloque_benef}"
            f"👉 Disponible en {destino}\n"
            f"🔗 Enlace en la bio ({bio_url}/bio)\n"
            f"📲 o mandanos un DM «QUIERO»\n\n"
            f"Enlace de afiliado: podemos recibir una comisión sin costo extra para vos.\n"
            f"La compra y la garantía las gestiona {destino}.\n\n"
            f".\n.\n.\n"
            f"{marketing.hashtags_producto(producto)} #Publicidad"
        )

    pv = producto.get("precio_venta") or 0
    if pv:
        precio = "$ " + f"{pv:,.0f}".replace(",", ".")
        linea_precio = f"💰 Precio: {precio}"
    else:
        linea_precio = "💰 Precio: consultanos por DM"

    return (
        f"🛒 {nombre}\n\n"
        f"{bloque_benef}"
        f"{linea_precio}\n"
        f"🚚 {marketing.ENVIO_TEXTO}\n"
        f"✅ Stock disponible\n\n"
        f"👉 Todos los productos en el link de la bio ({bio_url}/bio)\n"
        f"📲 o mandanos un DM «QUIERO»\n\n"
        f".\n.\n.\n"
        f"{marketing.hashtags_producto(producto)}"
    )


def postear_producto(producto_id, base_url="http://localhost:5000"):
    """Publica un producto en Instagram. Retorna (ok, msg)."""
    producto = db.get_producto(producto_id)
    if not producto:
        return False, "Producto no encontrado"

    imgs = db.get_imagenes(producto_id)
    if not imgs:
        return False, "Producto sin imagen"

    caption = construir_caption(producto)
    usar_reel = reels.disponible()
    msg_reel = ""

    if usar_reel:
        ok, msg = postear_reel(producto, caption, base_url)
        if ok:
            return True, f"reel:{msg}"
        # Si falla el reel, cae a foto para no perder la publicación.
        msg_reel = msg

    img_path = imgs[0]["archivo"]
    if not img_path.startswith("http"):
        img_url = f"{base_url.rstrip('/')}/{img_path.lstrip('/')}"
    else:
        img_url = img_path

    ok, msg = postear_foto(img_url, caption)
    if not ok and usar_reel:
        return False, f"reel: {msg_reel} | foto: {msg}"
    return ok, msg


def verificar_conexion():
    """Verifica que el token e IG Business ID sean válidos."""
    token, ig_id = _get_config()
    if not token:
        return False, "FB_PAGE_TOKEN no configurado"
    if not ig_id:
        return False, "IG_BUSINESS_ID no configurado"

    try:
        result = _api_call("GET", f"{ig_id}", params={"fields": "id,name,username"})
        return True, f"✅ Conectado a @{result.get('username', '?')}"
    except InstagramError as e:
        return False, str(e)
