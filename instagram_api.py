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
import logging
import os
import time
import urllib.request
import urllib.error
import urllib.parse

import config
import db

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
        raise InstagramError(f"HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise InstagramError(f"Error de conexión: {e.reason}")


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


def postear_producto(producto_id, base_url="http://localhost:5000"):
    """Publica un producto en Instagram. Retorna (ok, msg)."""
    producto = db.get_producto(producto_id)
    if not producto:
        return False, "Producto no encontrado"

    imgs = db.get_imagenes(producto_id)
    if not imgs:
        return False, "Producto sin imagen"

    img_path = imgs[0]["archivo"]
    if not img_path.startswith("http"):
        img_url = f"{base_url.rstrip('/')}/{img_path.lstrip('/')}"
    else:
        img_url = img_path

    pv = producto.get("precio_venta") or 0
    precio = f"$ {pv:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    wa = config.get("TIENDA_WA") or "https://wa.me/5491126268359"

    caption = (
        f"🛒 {producto['nombre']}\n\n"
        f"💰 Precio: {precio}\n"
        f"🚚 Envío gratis - 24 hs hábiles\n\n"
        f"📲 Comprá por WhatsApp: wa.me/{wa.replace('https://wa.me/', '')}\n\n"
        f".\n.\n.\n"
        f"#ClickYa #TiendaOnline #EnviosGratis #Argentina"
    )

    return postear_foto(img_url, caption)


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
