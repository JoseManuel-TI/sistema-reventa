"""Tests del parser de mensajes de grupos de WhatsApp."""

from importar_whatsapp import _parse_precio, parsear_mensaje

MENSAJE = """🔥 Excelente oportunidad para reventa

AIRE ACONDICIONADO RCA 3400W

💨 ¡Prepará tu hogar para el calor!
✅ Potencia de refrigeración: 3400W
✅ Ideal para climatizar ambientes del hogar
✅ Equivale aproximadamente a 2924 frigorías

🔹 PRECIO POR UNIDAD: $750.000

📲 ¡Consultamos por disponibilidad y más detalles!

HACÉ TU PEDIDO POR ESTE LINK 👇
https://wa.me/message/7WYN4OD7NZMYK1
"""


def test_parsear_mensaje_completo():
    r = parsear_mensaje(MENSAJE)
    assert r["nombre"] == "AIRE ACONDICIONADO RCA 3400W"
    assert r["costo"] == 750000.0
    assert r["stock"] == 0
    assert r["link"] == "https://wa.me/message/7WYN4OD7NZMYK1"
    assert "3400W" in r["beneficios"]
    assert "frigorías" in r["beneficios"]
    assert "Prepará tu hogar" in r["descripcion"]
    assert "$750.000" not in r["descripcion"]
    assert "wa.me" not in r["descripcion"]


def test_stock_detectado():
    r = parsear_mensaje("AURICULARES BT\nStock: 12 unidades\nPrecio $25.000")
    assert r["nombre"] == "AURICULARES BT"
    assert r["stock"] == 12
    assert r["costo"] == 25000.0


def test_nombre_evita_lineas_promocionales():
    r = parsear_mensaje("OFERTA MAYORISTA\nMi producto de prueba\n$1.500")
    assert r["nombre"] == "Mi producto de prueba"


def test_precios_formato_argentino():
    assert _parse_precio("750.000") == 750000.0
    assert _parse_precio("12.500") == 12500.0
    assert _parse_precio("1.234.567") == 1234567.0
    assert _parse_precio("750,50") == 750.5
    assert _parse_precio("1.234,56") == 1234.56
    assert _parse_precio("9.999") == 9999.0
