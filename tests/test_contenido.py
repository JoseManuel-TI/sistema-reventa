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


def test_productos_sin_instagram_reel_exitoso_no_es_candidato():
    _publicado(8)
    _log(8, "instagram", "reel:17841447050373553")
    assert 8 not in contenido.productos_sin_instagram()


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


def _producto(nombre, categoria, precio=50000):
    import db

    prov = db.get_proveedor_por_nombre("Test") or None
    prov_id = prov["id"] if prov else db.add_proveedor("Test")
    pid = db.add_producto(
        nombre=nombre,
        descripcion="",
        proveedor_id=prov_id,
        costo=precio / 1.35,
        categoria=categoria,
        stock=2,
        publicar=1,
    )
    db.update_producto(pid, precio_venta=precio)
    return pid


def test_programar_dos_diarias_una_por_categoria():
    _producto("Perfume A", "Perfumes")
    _producto("Perfume B", "Perfumes")
    _producto("Celular A", "Celulares")
    _producto("Celular B", "Celulares")

    creadas = contenido.programar_dos_diarias(dias=2, por_dia=2)

    assert len(creadas) == 4
    por_fecha = {}
    for c in creadas:
        por_fecha.setdefault(c["fecha"], []).append(c["producto"])
    for productos in por_fecha.values():
        assert len(productos) == 2
        assert sum("Perfume" in n for n in productos) == 1


def test_programar_dos_diarias_es_idempotente():
    _producto("Perfume A", "Perfumes")
    _producto("Celular A", "Celulares")

    assert len(contenido.programar_dos_diarias(dias=2, por_dia=2)) == 4
    assert contenido.programar_dos_diarias(dias=2, por_dia=2) == []


def test_rotacion_alterna_precios_accesibles_y_altos():
    productos = [
        {"id": 1, "precio_venta": 30000},
        {"id": 2, "precio_venta": 45000},
        {"id": 3, "precio_venta": 100000},
        {"id": 4, "precio_venta": 500000},
    ]
    assert [p["id"] for p in contenido._alternar_precios(productos)] == [1, 3, 2, 4]


def test_reorganizar_cola_futura_conserva_perfume_y_fechas():
    altos = [_producto("Alto A", "Audio", 200000), _producto("Alto B", "Hogar", 300000)]
    bajos = [_producto("Bajo A", "Audio", 20000), _producto("Bajo B", "Hogar", 30000)]
    perfume = _producto("Perfume A", "Perfumes", 70000)
    conn = _conn()
    for i, pid in enumerate([altos[0], perfume, altos[1], bajos[0], bajos[1]], 1):
        conn.execute(
            "INSERT INTO publicaciones (producto_id, programada_para, caption) "
            "VALUES (?, date('now', ?), ?)",
            (pid, f"+{i} day", f"texto {pid}"),
        )
    conn.commit()
    conn.close()

    assert contenido.alternar_precios_pendientes() == 4
    conn = _conn()
    filas = conn.execute("SELECT producto_id, programada_para, caption FROM publicaciones ORDER BY id").fetchall()
    conn.close()
    assert [f[0] for f in filas] == [bajos[0], perfume, altos[0], bajos[1], altos[1]]
    assert len({f[1] for f in filas}) == 5
    assert all(f[2] == f"texto {f[0]}" for f in filas)
    assert contenido.alternar_precios_pendientes() == 0


def test_republicar_instagram_sin_configurar(monkeypatch):
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: False)
    ok, fallidos, detalle = contenido.republicar_instagram()
    assert ok == 0
    assert fallidos == 0
    assert detalle[0][1] == "Instagram no configurado"
