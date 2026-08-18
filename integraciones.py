"""
Integraciones — fetch de metadata de URLs (Amazon/afiliados) y helpers de moneda.
Stdlib only: urllib + html.parser (sin dependencias pip).
"""

import re
import json
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

TIPO_PRODUCTO_LABELS = {
    "fisico_local": "Stock Local (AMBA)",
    "afiliado_digital": "Curso / Digital",
    "amazon_affiliate": "Importado Amazon",
    "otro": "Otro",
}

PLATAFORMA_LABELS = {
    "amazon": "Amazon",
    "aliexpress": "AliExpress",
    "mercadolibre": "Mercado Libre Afiliados",
    "hotmart": "Hotmart",
    "otro": "Otra plataforma",
}


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.titles = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            prop = attrs.get("property") or attrs.get("name") or ""
            content = attrs.get("content")
            key = prop.lower()
            if content is not None and (key.startswith("og:") or key in (
                    "description", "twitter:image", "twitter:title")):
                self.meta.setdefault(key, content)
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self.titles.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def _fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _decode(body):
    for enc in ("utf-8", "latin-1"):
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "replace")


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\|\s*$", "", text)
    return text


def fetch_metadata(url):
    """
    Extrae título, imagen y precio de una URL pública (Amazon, Tiendamia,
    Hotmart, etc.) usando OpenGraph. Devuelve dict con nombre, imagen, precio.
    Nunca lanza excepción: en error devuelve datos parciales.
    """
    resultado = {"nombre": "", "imagen": "", "precio": None, "descripcion": "", "ok": False}
    try:
        body = _fetch(url)
        html = _decode(body)
        parser = _MetaParser()
        parser.feed(html)
        meta = parser.meta

        nombre = (meta.get("og:title") or meta.get("twitter:title")
                  or (parser.titles[0] if parser.titles else ""))
        imagen = meta.get("og:image") or meta.get("twitter:image") or ""
        descripcion = meta.get("og:description") or meta.get("description") or ""

        resultado["nombre"] = _clean(nombre)
        resultado["imagen"] = _clean(imagen)
        resultado["descripcion"] = _clean(descripcion)
        resultado["precio"] = _parse_precio_meta(meta)
        resultado["ok"] = bool(resultado["nombre"])
        return resultado
    except Exception:
        return resultado


def _parse_precio_meta(meta):
    """Busca price:amount / og:price en las meta tags y lo devuelve como float."""
    for key in ("product:price:amount", "og:price:amount", "og:price"):
        val = meta.get(key)
        if val:
            try:
                num = re.sub(r"[^\d.,]", "", val).replace(",", ".")
                num = re.sub(r"\.(?=.*\.)", "", num)
                return float(num)
            except ValueError:
                pass
    return None


def detectar_plataforma(url):
    """Devuelve la plataforma estimada según el hostname de la URL."""
    host = (url or "").lower()
    if "amazon" in host or "amzn.to" in host:
        return "amazon"
    if "aliexpress" in host:
        return "aliexpress"
    if "mercadolibre" in host or "mercadolivre" in host:
        return "mercadolibre"
    if "hotmart" in host:
        return "hotmart"
    return "otro"


def inferir_tipo_producto(url=""):
    """Heurística para sugerir tipo_producto según la URL pegada."""
    if not url:
        return "fisico_local"
    plataforma = detectar_plataforma(url)
    if plataforma in ("amazon", "aliexpress", "mercadolibre"):
        return "amazon_affiliate"
    if plataforma == "hotmart":
        return "afiliado_digital"
    if any(k in url.lower() for k in ("udemy", "coursera", "hotmart", "teachable")):
        return "afiliado_digital"
    return "amazon_affiliate"


def tipo_label(tipo):
    return TIPO_PRODUCTO_LABELS.get(tipo or "", tipo or "")


def plataforma_label(plataforma):
    return PLATAFORMA_LABELS.get(plataforma or "", plataforma or "")


def convertir_precio_a_ars(valor, moneda, dolar_blue=None):
    """Convierte un precio a ARS si moneda es USD. Si ya es ARS lo devuelve igual."""
    if not valor or moneda in ("ARS", ""):
        return valor
    if dolar_blue is None:
        import precios as pcalc
        dolar_blue = pcalc.get_dolar_blue()
    return round(float(valor) * dolar_blue, 2)


def es_externo(tipo_producto):
    """Un producto externo (afiliado/Amazon) no usa carrito ni stock local."""
    return tipo_producto in ("afiliado_digital", "amazon_affiliate")


def producto_url_externa(producto):
    """Devuelve la URL externa a usar (external_url o link_afiliado)."""
    url = (producto.get("external_url") or producto.get("link_afiliado") or "").strip()
    return url or None


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not url:
        print("Uso: python integraciones.py <URL>")
        sys.exit(1)
    print(json.dumps(fetch_metadata(url), indent=2, ensure_ascii=False))
