"""Public shop: catalog, cart, checkout, bank transfer payment."""

import hashlib
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
import db
import feriados
import integraciones as itgr
import notificaciones

tienda = Blueprint("tienda", __name__, template_folder="templates")

def _store_name():
    return config.get("TIENDA_NOMBRE") or "Mi Tienda"
STORE_WA = config.whatsapp()

# Horas que se reserva el stock de un pedido pendiente antes de liberarlo.
try:
    RESERVA_HORAS = int(config.get("RESERVA_HORAS") or 24)
except (TypeError, ValueError):
    RESERVA_HORAS = 24

METODOS_PAGO = {
    "transferencia": "Transferencia bancaria",
    "contra_entrega": "Contra entrega (efectivo o transferencia al recibir)",
}

# Zonas de envío con costo fijo. El interior se cotiza por WhatsApp.
ZONAS_ENVIO = ["caba", "gba", "interior"]


def _numero(valor, default=0.0):
    """Convierte un valor de config ('3500', '3.500', 3500) a float."""
    if valor is None:
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^0-9.,-]", "", str(valor)).replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except (TypeError, ValueError):
        return default


def _envio_costo(zona):
    """Costo de envío según la zona elegida ('caba', 'gba', 'interior')."""
    if zona == "caba":
        return round(_numero(config.get("ENVIO_CABA")), 2)
    if zona == "gba":
        return round(_numero(config.get("ENVIO_GBA")), 2)
    return 0.0


def _zonas_envio():
    return [
        {"key": "caba", "label": "CABA (Capital Federal)", "costo": _envio_costo("caba")},
        {"key": "gba", "label": "GBA (Gran Buenos Aires)", "costo": _envio_costo("gba")},
        {"key": "interior", "label": "Interior / otra zona (a cotizar por WhatsApp)", "costo": 0.0, "a_cotizar": True},
    ]


# ─── Auditorio público: categorías por slug (ClickYa) ──────────────
GRUPOS_CATEGORIAS = {
    "tech": {
        "titulo": "Tech & Celulares",
        "subtitulo": "Smartphones, audio y accesorios de última generación.",
        "icono": "📱",
        "categorias": ["Celulares", "Audio", "Accesorios"],
    },
    "gadgets": {
        "titulo": "Gadgets & Accesorios",
        "subtitulo": "Accesorios, audio y wearables que simplifican tu día.",
        "icono": "⌚",
        "categorias": ["Accesorios", "Audio", "Celulares"],
    },
    "hogar-inteligente": {
        "titulo": "Hogar Inteligente",
        "subtitulo": "Electrodomésticos y calefacción para un hogar más cómodo.",
        "icono": "🏠",
        "categorias": ["Hogar", "Calefacción"],
    },
    "deportes": {
        "titulo": "Deportes & Fitness",
        "subtitulo": "Equipamiento para entrenar en casa sin excusas.",
        "icono": "💪",
        "categorias": ["Deportes"],
    },
}
NAV_CATEGORIAS = list(GRUPOS_CATEGORIAS)

_CSS_PATH = os.path.join(os.path.dirname(__file__), "static", "tienda.css")
CSS_VERSION = str(int(os.path.getmtime(_CSS_PATH))) if os.path.exists(_CSS_PATH) else "1"

CARRITO_KEY = "carrito"


def _get_carrito():
    return session.get(CARRITO_KEY, {})


def _save_carrito(data):
    session.pop("checkout_key", None)
    session[CARRITO_KEY] = data
    session.modified = True


def _refresh_carrito():
    carrito = _get_carrito()
    refreshed = {}
    changed = False
    for key, item in carrito.items():
        p = db.get_producto(item["producto_id"])
        if (not p or not p.get("activo") or not p.get("publicar") or _es_externo(p)
                or not p.get("precio_venta") or p["precio_venta"] <= 0 or (p.get("stock") or 0) <= 0):
            changed = True
            continue
        updated = dict(item, nombre=p["nombre"], precio=p["precio_venta"], stock=p["stock"],
                       cantidad=min(item["cantidad"], p["stock"]))
        changed |= updated != item
        refreshed[key] = updated
    if changed:
        _save_carrito(refreshed)
        flash("Actualizamos el carrito según los precios y el stock disponibles. Revisá el total.", "info")
    return refreshed


def _cantidad_form():
    try:
        cantidad = int(request.form.get("cantidad", 1))
        if cantidad < 1:
            raise ValueError
        return cantidad
    except (ValueError, TypeError):
        abort(400, description="La cantidad debe ser un número entero mayor a cero.")


def _cant_carrito():
    return sum(i["cantidad"] for i in _get_carrito().values())


def _wa_con_texto(texto):
    """Arma un link de WhatsApp con mensaje pre-cargado."""
    base = (STORE_WA or "").strip()
    if not base:
        return ""
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}text={quote(texto)}"


def _track_item(pid, nombre, precio, cantidad):
    """Arma el payload de un ítem para Meta Pixel / GA4."""
    pid = str(pid)
    precio = round(float(precio or 0), 2)
    return {
        "content_ids": [pid],
        "contents": [{"id": pid, "quantity": cantidad, "item_price": precio}],
        "items": [{"item_id": pid, "item_name": nombre, "price": precio, "quantity": cantidad}],
    }


def _track_carrito(carrito):
    data = {"value": 0.0, "content_ids": [], "contents": [], "items": []}
    total = 0.0
    for k, it in carrito.items():
        pid = it.get("producto_id") or k
        item = _track_item(pid, it["nombre"], it["precio"], it["cantidad"])
        data["content_ids"] += item["content_ids"]
        data["contents"] += item["contents"]
        data["items"] += item["items"]
        total += float(it["precio"]) * it["cantidad"]
    data["value"] = round(total, 2)
    return data


def _resumen_pedido(pedido, items):
    """Texto plano con el resumen del pedido (para WhatsApp)."""
    metodo = METODOS_PAGO.get(pedido.get("metodo_pago") or "transferencia", "Transferencia bancaria")
    lineas = "\n".join(
        f"• {i['nombre']} x{i['cantidad']} — {_pesos(i['subtotal'])}" for i in items
    )
    entrega = _direccion_completa(pedido)
    partes = [
        f"Pedido #{pedido['id']}",
        lineas,
        f"Total: {_pesos(pedido['total'])}",
        f"Pago: {metodo}",
    ]
    if entrega:
        partes.append(f"Entrega: {entrega}")
    return "\n".join(partes)


def _direccion_completa(pedido):
    """Arma la dirección de entrega con entre calles, localidad y CP si existen."""
    partes = [pedido.get("cliente_direccion") or ""]
    if pedido.get("cliente_entre_calles"):
        partes.append(f"entre {pedido['cliente_entre_calles']}")
    if pedido.get("cliente_localidad"):
        partes.append(pedido["cliente_localidad"])
    if pedido.get("cliente_codigo_postal"):
        partes.append(f"CP {pedido['cliente_codigo_postal']}")
    return ", ".join(p for p in partes if p)


def _notificar_nuevo_pedido(pedido_id):
    """Avisa al vendedor por Telegram apenas entra un pedido (para actuar rápido)."""
    pedido = db.get_pedido(pedido_id)
    if not pedido:
        return
    items = db.get_pedido_items(pedido_id)
    metodo = METODOS_PAGO.get(pedido.get("metodo_pago") or "transferencia", "Transferencia bancaria")
    lineas = "\n".join(f"  • {i['nombre']} x{i['cantidad']}" for i in items)
    zona = {"caba": "CABA", "gba": "GBA", "interior": "Interior"}.get(pedido.get("zona_envio"), "—")
    msg = (
        f"🛒 <b>NUEVO PEDIDO #{pedido_id}</b>\n"
        f"Pago: <b>{metodo}</b>\n\n"
        f"👤 {pedido['cliente_nombre']}\n"
        f"📱 {pedido.get('cliente_telefono') or '—'}\n"
        f"📧 {pedido.get('cliente_email') or '—'}\n"
        f"🏠 {_direccion_completa(pedido) or '—'}\n"
        f"🚚 Zona: {zona}\n\n"
        f"{lineas}\n\n"
        f"<b>Total: {_pesos(pedido['total'])}</b>"
    )
    notificaciones.telegram(msg)


DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _es_feriado(dia):
    """True si la fecha figura en los feriados configurados (/configuracion)."""
    return dia.strftime("%Y-%m-%d") in feriados.parsear(config.get("FERIADOS"))


def _es_dia_habil(dia):
    """Entregamos de lunes a viernes, salvo feriados."""
    return dia.weekday() < 5 and not _es_feriado(dia)


def _estimar_entrega(ahora=None):
    """Estima cuándo llega el pedido (CABA), salteando días no hábiles.

    - Día hábil antes del mediodía → 'hoy'
    - Día hábil a la tarde o fin de semana → próximo día hábil:
      'mañana' si es el día siguiente, o 'lunes 20/10' si queda más lejos.
    """
    if ahora is None:
        ahora = datetime.now()
    if _es_dia_habil(ahora) and ahora.hour < 12:
        return "hoy"

    dia = ahora + timedelta(days=1)
    while not _es_dia_habil(dia):
        dia += timedelta(days=1)

    if dia.date() == (ahora + timedelta(days=1)).date():
        return "mañana"
    return f"{DIAS_SEMANA[dia.weekday()]} {dia.strftime('%d/%m')}"


DELIVERY_INFO = config.get("DELIVERY_INFO") or "Se entrega dentro de las 24 hs hábiles posteriores a la confirmación del pago."


@tienda.context_processor
def inject_globals():
    logo = config.get("TIENDA_LOGO") or config.get("TIENDA_NOMBRE")
    return {
        "wa_link": config.get("TIENDA_WA"),
        "banco": config.get("BANCO"),
        "banco_titular": config.get("BANCO_TITULAR"),
        "banco_cbu": config.get("BANCO_CBU"),
        "banco_alias": config.get("BANCO_ALIAS"),
        "banco_tipo": config.get("BANCO_TIPO"),
        "banco_configurado": config.datos_bancarios_completos(),
        "tienda_logo": logo,
        "tienda_color": config.get("TIENDA_COLOR"),
        "tienda_descripcion": config.get("TIENDA_DESCRIPCION"),
        "delivery_info": config.get("DELIVERY_INFO"),
        "entrega_estimada": _estimar_entrega(),
        "cant_carrito": _cant_carrito(),
        "metodos_pago": METODOS_PAGO,
        "zonas_envio": _zonas_envio(),
        "meta_pixel_id": (config.get("META_PIXEL_ID") or "").strip(),
        "ga_id": (config.get("GA_MEASUREMENT_ID") or "").strip(),
        "public_url": (config.get("PUBLIC_URL") or "").rstrip("/"),
        "css_version": CSS_VERSION,
        "categorias": db.get_categorias(publicado_only=True),
        "nav_categorias": [
            {"slug": slug, **GRUPOS_CATEGORIAS[slug]} for slug in NAV_CATEGORIAS
        ],
        "origen_nav": ORIGEN_NAV,
        "origen_activa": request.args.get("origen", ""),
        "producto_beneficios": producto_beneficios,
        "producto_badge": producto_badge,
        "cta_producto": cta_producto,
        "producto_tipo_label": producto_tipo_label,
    }


# ─── Helpers de tipo de producto (local / digital / amazon) ────────

def _es_externo(p):
    """Un producto es externo si está marcado como afiliado o su tipo es digital/amazon."""
    return bool(p.get("es_afiliado")) or itgr.es_externo(p.get("tipo_producto"))


def producto_tipo_label(p):
    """Etiqueta corta del tipo de producto (para chips y cards)."""
    if _es_externo(p):
        tipo = p.get("tipo_producto")
        if tipo == "afiliado_digital":
            return "Curso / Digital"
        return "Importado Amazon"
    return "Stock Local (AMBA)"


def cta_producto(p):
    """Devuelve los datos del botón de compra según el tipo de producto."""
    tipo = p.get("tipo_producto")
    if _es_externo(p):
        url = itgr.producto_url_externa(p)
        plataforma = p.get("plataforma_afiliado") or itgr.detectar_plataforma(url or "")
        if tipo == "afiliado_digital" and plataforma == "hotmart":
            label, kicker = "Acceder al curso", "Curso digital de acceso inmediato"
        elif plataforma == "aliexpress":
            label, kicker = "Ver precio en AliExpress", "Precio actualizado en AliExpress"
        elif plataforma == "mercadolibre":
            label, kicker = "Ver oferta en Mercado Libre", "Precio actualizado en Mercado Libre"
        else:
            label, kicker = "Ver en Amazon", "Precio y envío calculados en Amazon"
        return {
            "url": url_for("tienda.out_afiliado", id=p["id"]) if url else url_for("tienda.producto", id=p["id"]),
            "label": label, "kicker": kicker, "externo": True,
            "tipo": tipo, "plataforma": plataforma,
        }
    return {
        "url": url_for("tienda.producto", id=p["id"]),
        "label": "Ver producto", "kicker": None, "externo": False,
        "tipo": tipo or "fisico_local", "plataforma": "",
    }


# ─── Helpers de card (afiliado/Amazon) ─────────────────────────────

def _norm_texto(s):
    """Normaliza texto: minúsculas y sin acentos (para comparar categorías)."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def _segmentos_beneficios(nombre):
    """Extrae frases de beneficio del nombre del producto.

    Los nombres suelen venir con ' - ' o ' | ' separando features:
        'Smartwatch Serie 10 - Pantalla Infinita + Notificaciones y Llamadas'
    Se toman los fragmentos descriptivos (todo menos la marca/nombre base).
    """
    if not nombre:
        return []
    partes = re.split(r"\s*-\s*|\s*\|\s*", nombre)
    beneficios = []
    for i, parte in enumerate(partes):
        if i == 0:
            continue
        for frag in re.split(r"\s*\+\s*|\s*/\s*", parte):
            frag = frag.strip(" (),;•")
            if not frag:
                continue
            clave = _norm_texto(frag)
            if not any(_norm_texto(b) == clave for b in beneficios):
                beneficios.append(frag)
    return beneficios


def producto_beneficios(p, cantidad=3):
    """Devuelve una lista corta (3) de beneficios clave para la card.

    Prioridad: campo manual `beneficios` (1 por línea o separados por ' | ')
    → descripción curada (por línea) → inferido del nombre.
    Completa con propuestas de valor genéricas.
    """
    def _limpiar(lineas):
        out = []
        for linea in lineas:
            linea = linea.strip(" -•\t·|").strip()
            if linea:
                out.append(linea)
        return out

    manual = (p.get("beneficios") or "").strip()
    if manual:
        lineas = []
        for parte in re.split(r"[|\n]", manual):
            lineas.extend(_limpiar([parte]))
        if lineas:
            return lineas[:cantidad]

    descripcion = (p.get("descripcion") or "").strip()
    if descripcion:
        lineas = _limpiar(descripcion.split("\n"))
        if len(lineas) >= cantidad:
            return lineas[:cantidad]

    ben = _segmentos_beneficios(p.get("nombre") or "")
    if _es_externo(p):
        extras = ["Compra 100% segura vía Amazon",
                  "Envío a Argentina disponible",
                  "Atención y soporte ClickYa"]
    else:
        extras = ["Stock disponible en AMBA",
                  "Entrega en 24 hs hábiles",
                  "Atención y soporte ClickYa"]
    i = 0
    while len(ben) < cantidad and i < len(extras):
        if extras[i] not in ben:
            ben.append(extras[i])
        i += 1
    return ben[:cantidad]


def producto_badge(p):
    """Etiqueta promocional de la card según categoría (solo prop, no canal).

    El canal (Local / Amazon Importado / Digital) se muestra aparte en el badge
    de tipo para no mezclar mensajes en la misma tarjeta.
    """
    cat = _norm_texto(p.get("categoria") or "")
    if cat in ("celulares", "deportes", "consolas"):
        return "Top Ventas"
    if cat in ("audio", "hogar", "calefacción", "calefaccion"):
        return "Recomendado"
    if cat in ("accesorios", "gadgets"):
        return "Nuevo Ingreso"
    return ""


def _pesos(val):
    if val is None:
        return "-"
    return f"$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _productos_con_imagen(productos):
    for p in productos:
        imgs = db.get_imagenes(p["id"])
        p["imagen"] = db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None
    return productos


# ─── Landing / Link-in-bio ─────────────────────────────────────────

@tienda.route("/")
def index():
    """Raíz: redirige directo al catálogo (sin página de inicio)."""
    return redirect(url_for("tienda.catalogo"))


@tienda.route("/bio")
def bio():
    """Vista móvil estilo Link-in-bio, separada de la home (punto de entrada desde redes sociales)."""
    productos = _productos_publicados()
    _productos_con_imagen(productos)
    return render_template("tienda/bio.html",
                           store_name=_store_name(),
                           destacados=productos[:6],
                           total_productos=len(productos))


@tienda.route("/nosotros")
def nosotros():
    """Página institucional: quiénes somos, pilares y compromisos."""
    return render_template("tienda/nosotros.html", store_name=_store_name())


@tienda.route("/envios")
def envios():
    """Página informativa: zonas de entrega, plazos, costos y devoluciones."""
    return render_template("tienda/envios.html", store_name=_store_name(),
                           envio_caba=_envio_costo("caba"),
                           envio_gba=_envio_costo("gba"))


# ─── Catálogo ──────────────────────────────────────────────────────

def _productos_publicados():
    productos = db.get_productos(publicado_only=True)
    return [p for p in productos
            if _es_externo(p) or (p.get("precio_venta") and p["precio_venta"] > 0)]


ORIGEN_LABELS = {
    "local": "Productos",
    "digital": "Cursos Digitales",
    "amazon": "Amazon Importados",
}

ORIGEN_NAV = [
    {"key": "local", "label": "Productos", "icono": "🚚"},
    {"key": "digital", "label": "Cursos Digitales", "icono": "💻"},
    {"key": "amazon", "label": "Amazon Importados", "icono": "📦"},
]


def _filtrar_origen(productos, origen):
    def tipo_de(p):
        tipo = p.get("tipo_producto")
        if tipo == "afiliado_digital" or (p.get("es_afiliado") and tipo != "amazon_affiliate"):
            return "digital"
        if tipo == "amazon_affiliate" or (p.get("es_afiliado") and p.get("plataforma_afiliado") == "amazon"):
            return "amazon"
        return "local"
    if not origen:
        return productos
    return [p for p in productos if tipo_de(p) == origen]


@tienda.route("/tienda")
def catalogo():
    cat = request.args.get("cat", "").strip()
    origen = request.args.get("origen", "").strip()
    productos = _productos_publicados()
    if cat:
        productos = [p for p in productos
                     if _norm_texto(p.get("categoria") or "") == _norm_texto(cat)]
    productos = _filtrar_origen(productos, origen)
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=_store_name(),
                           cat_activa="",
                           origen_activa=origen,
                           origen_labels=ORIGEN_LABELS,
                           grupo=None)


@tienda.route("/<slug>")
def categoria(slug):
    """Página de categoría destacada: /tech, /gadgets, /hogar-inteligente, /deportes."""
    grupo = GRUPOS_CATEGORIAS.get(slug)
    if not grupo:
        return redirect(url_for("tienda.catalogo"))
    cats = [_norm_texto(c) for c in grupo["categorias"]]
    productos = [
        p for p in _productos_publicados()
        if cats and _norm_texto(p.get("categoria") or "") in cats
    ]
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=_store_name(),
                           cat_activa=slug,
                           origen_activa="",
                           origen_labels=ORIGEN_LABELS,
                           grupo=grupo)


@tienda.route("/tienda/<int:id>")
def producto(id):
    p = db.get_producto(id)
    if not p or not (_es_externo(p)
                     or (p.get("precio_venta") and p["precio_venta"] > 0)):
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    imgs = db.get_imagenes(id)
    for i, img in enumerate(imgs):
        imgs[i]["archivo"] = db.normalizar_imagen(img["archivo"])
    track_data = None
    if not _es_externo(p) and p.get("precio_venta"):
        track_data = _track_item(p["id"], p["nombre"], p["precio_venta"], 1)
    return render_template("tienda/producto.html",
                           p=p, imagenes=imgs, track_data=track_data,
                           store_name=_store_name(), peso=_pesos)


@tienda.route("/s/<int:id>")
def enlace_corto(id):
    """URL corta para compartir: redirige a la ficha del producto."""
    p = db.get_producto(id)
    if not p or not (_es_externo(p)
                     or (p.get("precio_venta") and p["precio_venta"] > 0)):
        abort(404)
    return redirect(url_for("tienda.producto", id=id))


@tienda.route("/out/<int:id>")
def out_afiliado(id):
    """Registra el clic afiliado y redirige a la plataforma externa."""
    p = db.get_producto(id)
    if not p or not _es_externo(p):
        abort(404)
    destino = itgr.producto_url_externa(p)
    if not destino:
        return redirect(url_for("tienda.producto", id=id))

    plataforma = p.get("plataforma_afiliado") or itgr.detectar_plataforma(destino)
    origen = request.args.get("src", "").strip()[:40]
    ip_raw = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16] if ip_raw else ""
    try:
        db.registrar_click_afiliado(
            producto_id=id,
            plataforma=plataforma,
            destino=destino,
            origen=origen,
            referer=(request.referrer or "")[:500],
            user_agent=(request.user_agent.string or "")[:500],
            ip_hash=ip_hash,
        )
    except Exception:
        pass
    return redirect(destino)


# ─── Carrito ───────────────────────────────────────────────────────

@tienda.route("/carrito")
def ver_carrito():
    carrito = _refresh_carrito()
    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    return render_template("tienda/carrito.html",
                           carrito=carrito, total=total,
                           store_name=_store_name(), peso=_pesos)


@tienda.route("/carrito/agregar/<int:id>", methods=["POST"])
def carrito_agregar(id):
    p = db.get_producto(id)
    if not p or not p.get("activo") or not p.get("publicar") or not p.get("precio_venta") or p["precio_venta"] <= 0:
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    if _es_externo(p):
        flash("Este producto se compra en la plataforma externa.", "error")
        return redirect(url_for("tienda.producto", id=id))

    cantidad = _cantidad_form()
    stock = p.get("stock") or 0
    if stock == 0:
        flash("Producto agotado.", "error")
        return redirect(url_for("tienda.producto", id=id))
    if cantidad > stock:
        flash(f"Stock insuficiente. Disponible: {stock}", "error")
        return redirect(url_for("tienda.producto", id=id))

    imgs = db.get_imagenes(id)
    carrito = _get_carrito()
    key = str(id)
    if key in carrito:
        nueva = carrito[key]["cantidad"] + cantidad
        carrito[key]["cantidad"] = min(nueva, stock) if stock > 0 else nueva
    else:
        carrito[key] = {
            "nombre": p["nombre"],
            "precio": p["precio_venta"],
            "cantidad": cantidad,
            "imagen": db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None,
            "stock": stock,
            "producto_id": id,
        }
    _save_carrito(carrito)
    flash(f"{p['nombre']} agregado al carrito.", "success")
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/carrito/actualizar/<int:id>", methods=["POST"])
def carrito_actualizar(id):
    cantidad = _cantidad_form()
    carrito = _get_carrito()
    key = str(id)
    if key in carrito:
        stock = carrito[key].get("stock", 0)
        if stock > 0:
            cantidad = min(cantidad, stock)
        carrito[key]["cantidad"] = cantidad
        _save_carrito(carrito)
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/carrito/eliminar/<int:id>", methods=["POST"])
def carrito_eliminar(id):
    carrito = _get_carrito()
    carrito.pop(str(id), None)
    _save_carrito(carrito)
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/comprar-ahora/<int:id>", methods=["POST"])
def comprar_ahora(id):
    p = db.get_producto(id)
    if not p or not p.get("activo") or not p.get("publicar") or not p.get("precio_venta") or p["precio_venta"] <= 0:
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    if _es_externo(p):
        flash("Este producto se compra en la plataforma externa.", "error")
        return redirect(url_for("tienda.producto", id=id))

    cantidad = _cantidad_form()
    stock = p.get("stock") or 0
    if stock == 0:
        flash("Producto agotado.", "error")
        return redirect(url_for("tienda.producto", id=id))
    if cantidad > stock:
        flash(f"Stock insuficiente. Disponible: {stock}", "error")
        return redirect(url_for("tienda.producto", id=id))

    imgs = db.get_imagenes(id)
    _save_carrito({str(id): {
        "nombre": p["nombre"],
        "precio": p["precio_venta"],
        "cantidad": cantidad,
        "imagen": db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None,
        "stock": stock,
        "producto_id": id,
    }})
    return redirect(url_for("tienda.checkout"))


# ─── Checkout ──────────────────────────────────────────────────────

@tienda.route("/checkout")
def checkout():
    carrito = _refresh_carrito()
    session.setdefault("checkout_key", secrets.token_urlsafe(32))
    if not carrito:
        flash("El carrito está vacío.", "error")
        return redirect(url_for("tienda.catalogo"))
    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    zonas = _zonas_envio()
    return render_template("tienda/checkout.html",
                           carrito=carrito, total=total,
                           metodos_pago=METODOS_PAGO,
                           zonas_envio=zonas,
                           envio_default=zonas[0],
                           track_data=_track_carrito(carrito),
                           store_name=_store_name(), peso=_pesos)


@tienda.route("/checkout/procesar", methods=["POST"])
def checkout_procesar():
    checkout_key = request.form.get("checkout_key", "") or session.get("checkout_key", "")
    last = session.get("ultimo_checkout", {})
    if checkout_key and checkout_key == last.get("key"):
        return redirect(url_for("tienda.gracias", id=last["id"]))
    carrito = _get_carrito()
    if not carrito:
        flash("El carrito está vacío.", "error")
        return redirect(url_for("tienda.catalogo"))

    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip()
    telefono = request.form.get("telefono", "").strip()
    direccion = request.form.get("direccion", "").strip()
    entre_calles = request.form.get("entre_calles", "").strip()
    localidad = request.form.get("localidad", "").strip()
    codigo_postal = request.form.get("codigo_postal", "").strip()

    if not nombre or len(nombre) > 200 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254 or len(telefono) > 50 or len(direccion) > 500:
        flash("Completá nombre y email.", "error")
        return redirect(url_for("tienda.checkout"))
    if not telefono:
        flash("Completá el teléfono para coordinar la entrega.", "error")
        return redirect(url_for("tienda.checkout"))
    if not direccion:
        flash("Completá la dirección de entrega.", "error")
        return redirect(url_for("tienda.checkout"))
    if not codigo_postal:
        flash("Completá el código postal.", "error")
        return redirect(url_for("tienda.checkout"))

    metodo_pago = request.form.get("metodo_pago", "transferencia").strip()
    if metodo_pago not in METODOS_PAGO:
        metodo_pago = "transferencia"

    zona_raw = request.form.get("zona_envio")
    if zona_raw is None:
        zona_envio = ""
        envio_costo = 0
    else:
        zona_envio = zona_raw.strip()
        if zona_envio not in ZONAS_ENVIO:
            zona_envio = "caba"
        envio_costo = _envio_costo(zona_envio)

    reserva_expira = ""
    if RESERVA_HORAS > 0:
        reserva_expira = (datetime.now() + timedelta(hours=RESERVA_HORAS)).strftime("%Y-%m-%d %H:%M:%S")

    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    try:
        pedido_id = db.crear_pedido(nombre, email, telefono, direccion, total, carrito, checkout_key,
                                    metodo_pago=metodo_pago, reserva_expira=reserva_expira,
                                    zona_envio=zona_envio, envio_costo=envio_costo,
                                    cliente_entre_calles=entre_calles, cliente_localidad=localidad,
                                    cliente_codigo_postal=codigo_postal)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("tienda.ver_carrito"))

    _notificar_nuevo_pedido(pedido_id)
    session["pedidos_propios"] = (session.get("pedidos_propios", []) + [pedido_id])[-20:]
    session["ultimo_checkout"] = {"key": checkout_key, "id": pedido_id}

    _save_carrito({})

    # Recordamos el pedido en la sesión para que /gracias solo lo muestre a
    # quien efectivamente lo creó (evita enumerar datos personales por ID).
    mis_pedidos = session.get("mis_pedidos", [])
    mis_pedidos.append(pedido_id)
    session["mis_pedidos"] = mis_pedidos[-20:]
    session.modified = True

    return redirect(url_for("tienda.gracias", id=pedido_id))


# ─── Google Merchant Center XML Feed ─────────────────────────────

@tienda.route("/productos.xml")
def merchant_feed():
    productos = db.get_productos(publicado_only=True)
    productos = [p for p in productos if p.get("precio_venta") and p["precio_venta"] > 0]
    _productos_con_imagen(productos)

    from xml.sax.saxutils import escape

    from flask import Response

    store_name = _store_name()
    items = []
    for p in productos:
        imgs = db.get_imagenes(p["id"])
        img = db.normalizar_imagen(imgs[0]["archivo"]) if imgs else ""
        if img and not img.startswith("http"):
            img = request.host_url.rstrip("/") + "/" + img
        link = url_for("tienda.producto", id=p["id"], _external=True)
        desc = escape((p.get("descripcion") or p["nombre"])[:5000])
        name = escape(p["nombre"][:150])
        items.append(f"""    <item>
      <g:id>{p['id']}</g:id>
      <g:title>{name}</g:title>
      <g:description>{desc}</g:description>
      <g:link>{escape(link)}</g:link>
      <g:image_link>{escape(img)}</g:image_link>
      <g:availability>{'in_stock' if p.get('stock', 0) > 0 else 'out_of_stock'}</g:availability>
      <g:price>{p['precio_venta']:.2f} ARS</g:price>
      <g:condition>new</g:condition>
      <g:brand>{escape(store_name)}</g:brand>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">
  <channel>
    <title>{escape(store_name)}</title>
    <link>{request.host_url}</link>
    <description>{escape(store_name)} - Productos</description>
{chr(10).join(items)}
  </channel>
</rss>"""
    return Response(xml, mimetype="application/xml; charset=utf-8")


# ─── Confirmación ──────────────────────────────────────────────────

@tienda.route("/gracias/<int:id>")
def gracias(id):
    pedido = db.get_pedido(id)
    propio = (session.get("admin") or id in session.get("pedidos_propios", [])
              or id in session.get("mis_pedidos", []))
    if pedido and not propio:
        abort(404)
    if not pedido or id not in session.get("mis_pedidos", []):
        flash("Pedido no encontrado.", "error")
        return redirect(url_for("tienda.catalogo"))
    line_items = db.get_pedido_items(id)
    pedido["line_items"] = line_items
    wa_pedido = _wa_con_texto(_resumen_pedido(pedido, line_items))

    track_data = {"value": round(float(pedido["total"] or 0), 2), "transaction_id": str(pedido["id"]),
                  "content_ids": [], "contents": [], "items": []}
    for i in line_items:
        item = _track_item(i.get("producto_id") or i["nombre"], i["nombre"],
                           i["precio_unitario"], i["cantidad"])
        track_data["content_ids"] += item["content_ids"]
        track_data["contents"] += item["contents"]
        track_data["items"] += item["items"]

    return render_template("tienda/gracias.html",
                           pedido=pedido,
                           store_name=_store_name(),
                           wa_link=STORE_WA,
                           wa_pedido=wa_pedido,
                           track_data=track_data,
                           metodo_pago_label=METODOS_PAGO.get(
                               pedido.get("metodo_pago") or "transferencia", "Transferencia bancaria"),
                           peso=_pesos)

