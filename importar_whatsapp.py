"""Parser de ofertas de grupos de WhatsApp para carga rápida de productos.

Extrae nombre, costo, stock, beneficios y descripción de mensajes típicos de
proveedores mayoristas, sin depender de un formato fijo.
"""

import re

_URL_RE = re.compile(r"(https?://\S+|(?:www\.|wa\.me/)\S+)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([\d][\d.,]*)")
_STOCK_RE = re.compile(
    r"(?:stock|disponibles?|unidades?)\D{0,12}(\d{1,5})", re.IGNORECASE
)
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D"
    "\u2190-\u21FF\u2900-\u297F\uFE00-\uFE0F]+"
)
_PREFIJO_BULLET = re.compile(r"^\s*(?:[-•·*✅✔☑🟢🔵>»]+\s*)+")
_PREFIJO_BENEFICIO = re.compile(r"^\s*[✅✔☑🟢🔵]|^\s*[-•·*]\s+")

_PROMO = (
    "oportunidad", "oferta", "promo", "descuento", "envío", "envio",
    "consult", "precio", "mayorista", "reventa", "stock", "disponible",
    "liquidación", "liquidacion", "cuotas", "pedido", "link",
)
_RUIDO = (
    "leer más", "leer mas", "administradores pueden enviar",
    "pueden enviar mensajes",
)
_CTA_RE = re.compile(
    r"(pedido|pedí|pedi|pide).{0,25}(link|l[íi]nea)|link.{0,25}(pedido|comprar)",
    re.IGNORECASE,
)


def _limpiar(linea):
    linea = _EMOJI_RE.sub(" ", linea or "")
    linea = linea.replace("\u00a0", " ").replace("\u2063", "")
    linea = _PREFIJO_BULLET.sub("", linea)
    linea = re.sub(r"\s+", " ", linea)
    return linea.strip(" \t-–—|·:").strip()


def _parse_precio(texto):
    """Interpreta montos en formato argentino (punto de miles, coma decimal)."""
    if texto is None:
        return None
    s = str(texto).strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            s = "".join(partes)
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _es_promo(texto):
    low = texto.lower()
    return any(p in low for p in _PROMO)


def _es_ruido(texto):
    low = texto.lower()
    return any(r in low for r in _RUIDO)


def parsear_mensaje(texto):
    """Devuelve dict con nombre, descripcion, beneficios, costo, stock y link."""
    pares = []
    for raw in (texto or "").splitlines():
        limpio = _limpiar(raw)
        if limpio:
            pares.append((raw, limpio))

    nombre = ""
    idx_nombre = -1
    for i, (_raw, limpio) in enumerate(pares):
        if _URL_RE.search(limpio) or _es_promo(limpio) or _es_ruido(limpio):
            continue
        if len(limpio) < 5:
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3}", limpio):
            continue
        nombre = limpio[:90].strip()
        idx_nombre = i
        break

    if not nombre and pares:
        nombre = pares[0][1][:90].strip()
        idx_nombre = 0

    costo = None
    for raw, _ in pares:
        m = _PRICE_RE.search(raw)
        if m:
            costo = _parse_precio(m.group(1))
            break

    stock = 0
    for raw, _ in pares:
        m = _STOCK_RE.search(raw)
        if m:
            stock = int(m.group(1))
            break

    link = ""
    m = _URL_RE.search(texto or "")
    if m:
        link = m.group(1).rstrip(".,;:)")

    descripcion = []
    beneficios = []
    for i, (raw, limpio) in enumerate(pares):
        if i <= idx_nombre:
            continue
        if _PRICE_RE.search(raw) or _URL_RE.search(limpio):
            continue
        if _es_ruido(limpio) or _CTA_RE.search(limpio):
            continue
        if _PREFIJO_BENEFICIO.match(raw):
            beneficios.append(limpio)
        else:
            descripcion.append(limpio)

    return {
        "nombre": nombre,
        "descripcion": "\n".join(descripcion).strip(),
        "beneficios": "\n".join(beneficios).strip(),
        "costo": costo,
        "stock": stock,
        "link": link,
    }
