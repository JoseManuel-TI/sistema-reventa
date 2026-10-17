from datetime import datetime

import pytest

import tienda


@pytest.mark.parametrize("momento,esperado", [
    # Viernes por la mañana -> se entrega hoy
    (datetime(2026, 10, 16, 9, 0), "hoy"),
    (datetime(2026, 10, 16, 11, 59), "hoy"),
    # Viernes al mediodía/tarde -> salta el finde, llega el lunes
    (datetime(2026, 10, 16, 12, 0), "lunes 19/10"),
    (datetime(2026, 10, 16, 18, 0), "lunes 19/10"),
    # Sábado y domingo -> próximo día hábil (lunes)
    (datetime(2026, 10, 17, 9, 0), "lunes 19/10"),
    (datetime(2026, 10, 17, 20, 0), "lunes 19/10"),
    # Domingo -> el día siguiente (lunes) sí es hábil
    (datetime(2026, 10, 18, 10, 0), "mañana"),
    # Lunes por la mañana -> hoy
    (datetime(2026, 10, 19, 8, 0), "hoy"),
    # Lunes después de las 12 -> mañana (martes)
    (datetime(2026, 10, 19, 12, 0), "mañana"),
    (datetime(2026, 10, 19, 17, 30), "mañana"),
])
def test_estimar_entrega_saltea_fin_de_semana(momento, esperado):
    assert tienda._estimar_entrega(momento) == esperado


def test_envio_costo_por_zona():
    assert tienda._envio_costo("caba") == 3500.0
    assert tienda._envio_costo("gba") == 5500.0
    assert tienda._envio_costo("interior") == 0.0
    assert tienda._envio_costo("desconocida") == 0.0


def test_zonas_envio_estructura():
    zonas = tienda._zonas_envio()
    assert [z["key"] for z in zonas] == ["caba", "gba", "interior"]
    assert zonas[0]["costo"] == 3500.0
    assert zonas[2].get("a_cotizar") is True


def test_numero_parsea_formato_argentino():
    assert tienda._numero("3.500") == 3500.0
    assert tienda._numero("5500") == 5500.0
    assert tienda._numero("3.500,50") == 3500.5
    assert tienda._numero("", default=0.0) == 0.0
