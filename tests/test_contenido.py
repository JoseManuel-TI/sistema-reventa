"""Tests de la cola de contenido y republicación en Instagram."""

import pytest

import contenido


@pytest.fixture(autouse=True)
def _limpiar_contenido():
    contenido._init_db()
    conn = contenido._get_conn()
    conn.execute("DELETE FROM publicaciones")
    conn.execute("DELETE FROM contenido_log")
    conn.commit()
    conn.close()
    yield


def _conn():
    contenido._init_db()
    return contenido._get_conn()


def _publicado(producto_id, cuando="2026-10-19 10:00:00"):
    conn = _conn()
    conn.execute(
        "INSERT INTO publicaciones (producto_id, estado, programada_para, publicada_en) "
        "VALUES (?, 'publicado', ?, ?)",
        (producto_id, cuando, cuando),
    )
    conn.commit()
    conn.close()


def _log(producto_id, canal, resultado):
    conn = _conn()
    conn.execute(
        "INSERT INTO contenido_log (producto_id, canal, resultado) VALUES (?, ?, ?)",
        (producto_id, canal, resultado),
    )
    conn.commit()
    conn.close()


def test_productos_sin_instagram_incluye_fallidos():
    _publicado(1)
    _log(1, "instagram", "API access blocked")
    _publicado(2)
    _log(2, "instagram", "17841447050373553")
    assert contenido.productos_sin_instagram() == [1]


def test_productos_sin_instagram_incluye_sin_log():
    _publicado(5)
    assert 5 in contenido.productos_sin_instagram()


def test_republicar_instagram_ok(monkeypatch):
    _publicado(1)
    _log(1, "instagram", "API access blocked")
    monkeypatch.setattr(contenido, "PAUSA_ENTRE_POSTEOS", 0)
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: True)
    monkeypatch.setattr(
        contenido.instagram_api, "postear_producto", lambda pid, base_url="x": (True, "98765")
    )

    ok, fallidos, detalle = contenido.republicar_instagram()

    assert ok == 1
    assert fallidos == 0
    assert detalle == [(1, "98765")]
    assert contenido.productos_sin_instagram() == []


def test_republicar_instagram_falla_y_reintenta(monkeypatch):
    _publicado(3)
    monkeypatch.setattr(contenido, "PAUSA_ENTRE_POSTEOS", 0)
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: True)
    monkeypatch.setattr(
        contenido.instagram_api, "postear_producto", lambda pid, base_url="x": (False, "blocked")
    )

    ok, fallidos, _ = contenido.republicar_instagram()

    assert ok == 0
    assert fallidos == 1
    assert 3 in contenido.productos_sin_instagram()


def test_republicar_instagram_sin_configurar(monkeypatch):
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: False)
    ok, fallidos, detalle = contenido.republicar_instagram()
    assert ok == 0
    assert fallidos == 0
    assert detalle[0][1] == "Instagram no configurado"
