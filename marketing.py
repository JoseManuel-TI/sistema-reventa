"""Textos de marketing reutilizables (hashtags, beneficios, envíos).

Centraliza el copy que usan Telegram (`contenido.generar_caption`) e Instagram
(`instagram_api`), para que un cambio de mensaje o de hashtags se haga en un solo
lugar.
"""

import re
import unicodedata

# Hashtags base (ver docs/marketing/copies_instagram_facebook.md)
HASHTAGS_BASE = [
    "#clickya", "#comprasargentina", "#tiendaonline", "#amba",
    "#caba", "#gba", "#enviolocal", "#compraenargentina",
]

ENVIO_TEXTO = "Envíos a CABA y GBA · entrega en 24 h"


def _slug_hashtag(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", t)


def hashtags_producto(producto, extra=None, limite=15):
    """Hashtags base + categoría + 2 palabras del nombre + extras (sin repetir)."""
    tags = list(HASHTAGS_BASE)

    categoria = _slug_hashtag(producto.get("categoria"))
    if len(categoria) >= 3:
        tags.append("#" + categoria)

    palabras = [
        _slug_hashtag(p)
        for p in re.split(r"\s+", producto.get("nombre") or "")
        if len(_slug_hashtag(p)) >= 4
    ]
    tags.extend("#" + p for p in palabras[:2])
    tags.extend("#" + _slug_hashtag(e) for e in (extra or []))

    vistos, salida = set(), []
    for t in tags:
        clave = t.lower()
        if len(t) > 4 and clave not in vistos:
            vistos.add(clave)
            salida.append(t)
    return " ".join(salida[:limite])


def lineas_beneficios(producto, maximo=4):
    """Beneficios del producto como lista corta (1 por línea o separados por '|')."""
    partes = re.split(r"[\n|]+", producto.get("beneficios") or "")
    salida = []
    for parte in partes:
        limpio = parte.strip().lstrip("-•·*✅✔☑🔹 \t").strip()
        if limpio:
            salida.append(limpio)
    return salida[:maximo]
