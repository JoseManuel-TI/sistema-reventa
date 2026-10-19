"""Tests de los textos de marketing (hashtags, beneficios, captions)."""

import contenido
import instagram_api
import marketing


def _producto(**extra):
    base = {
        "id": 7,
        "nombre": "Parlante Bluetooth JBL Go 3",
        "descripcion": "Sonido potente y portátil.",
        "beneficios": "Resistente al agua\nBatería 5 h|Carga rápida USB-C",
        "categoria": "Audio",
        "precio_venta": 33750.0,
        "tipo_producto": "fisico_local",
        "es_afiliado": 0,
    }
    base.update(extra)
    return base


def test_hashtags_incluyen_base_categoria_y_nombre():
    tags = marketing.hashtags_producto(_producto())
    assert "#clickya" in tags
    assert "#Audio" in tags
    assert "#Parlante" in tags


def test_hashtags_sin_repetir_y_respetan_limite():
    tags = marketing.hashtags_producto(_producto(), extra=["Audio", "oferta"], limite=5).split()
    assert len(tags) == 5
    assert len({t.lower() for t in tags}) == 5


def test_lineas_beneficios_separa_y_limpia():
    benef = marketing.lineas_beneficios(_producto())
    assert benef == ["Resistente al agua", "Batería 5 h", "Carga rápida USB-C"]


def test_lineas_beneficios_vacio():
    assert marketing.lineas_beneficios({"beneficios": ""}) == []


def test_caption_instagram_no_dice_envio_gratis():
    caption = instagram_api.construir_caption(_producto())
    assert "Envío gratis" not in caption
    assert marketing.ENVIO_TEXTO in caption
    assert "33.750,00" in caption
    assert "Resistente al agua" in caption
    assert "link de la bio" in caption
    assert "#clickya" in caption


def test_caption_instagram_sin_precio():
    caption = instagram_api.construir_caption(_producto(precio_venta=0))
    assert "consultanos por DM" in caption
    assert "Precio: $" not in caption


def test_caption_telegram_tiene_link_y_sin_envio_gratis():
    caption = contenido.generar_caption(_producto())
    assert "Envío gratis" not in caption
    assert "Comprar por WhatsApp" in caption
    assert "/tienda/7" in caption
    assert "33.750,00" in caption
