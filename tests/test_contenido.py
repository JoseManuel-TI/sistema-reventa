"""Tests de la cola de contenido y republicación en Instagram."""

import pytest

import contenido


@pytest.fixture(autouse=True)
def _limpiar_contenido():
    contenido._init_db()
    conn = contenido._get_conn()
    conn.execute("DELETE FROM publicaciones")
    conn.execute("DELETE FROM contenido_log")
    conn.execute("DELETE FROM contenido_estado")
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


def _programar(producto_id, dias=0):
    conn = _conn()
    conn.execute(
        "INSERT INTO publicaciones (producto_id, programada_para, caption) "
        "VALUES (?, date('now', ?), 'texto')",
        (producto_id, f"{dias:+d} day"),
    )
    conn.commit()
    conn.close()


def _estado(producto_id):
    conn = _conn()
    row = conn.execute(
        "SELECT estado FROM publicaciones WHERE producto_id=? ORDER BY id DESC LIMIT 1",
        (producto_id,),
    ).fetchone()
    conn.close()
    return row[0]


def test_producto_publicable_exige_existencia_fisica():
    base = {
        "publicar": 1,
        "activo": 1,
        "precio_venta": 100,
        "stock": 5,
        "tipo_producto": "fisico_local",
    }
    assert contenido._producto_publicable(base)
    assert not contenido._producto_publicable({**base, "inventario_origen": "proveedor"})
    assert not contenido._producto_publicable(
        {**base, "inventario_origen": "propio", "stock_fisico": 0}
    )
    assert contenido._producto_publicable(
        {**base, "inventario_origen": "propio", "stock_fisico": 2}
    )
    assert not contenido._producto_publicable({**base, "es_afiliado": 1})


def test_programar_todos_solo_fisicos_con_stock():
    import db

    fisico = _producto("Fisico", "Audio")
    sin_stock = _producto("Sin stock", "Audio")
    db.update_producto(sin_stock, stock=0)
    externo = _producto("Externo", "Amazon")
    db.update_producto(externo, stock=1, es_afiliado=1, tipo_producto="amazon_affiliate")

    assert contenido.programar_todos() == 1

    conn = _conn()
    programados = [r[0] for r in conn.execute("SELECT producto_id FROM publicaciones").fetchall()]
    conn.close()
    assert programados == [fisico]
    assert contenido.programar_todos() == 0


def test_publicar_pendientes_solo_fisicos_con_stock(monkeypatch):
    import db

    fisico = _producto("Fisico", "Audio")
    sin_stock = _producto("Sin stock", "Audio")
    db.update_producto(sin_stock, stock=0)
    externo = _producto("Externo", "Amazon")
    db.update_producto(externo, stock=1, es_afiliado=1, tipo_producto="amazon_affiliate")
    _programar(sin_stock, dias=-2)
    _programar(externo, dias=-1)
    _programar(fisico)

    publicados = []

    def _postear(producto, caption=None):
        publicados.append(producto["id"])
        return True, "OK"

    monkeypatch.setattr(contenido, "PAUSA_ENTRE_POSTEOS", 0)
    monkeypatch.setattr(contenido, "postear_telegram", _postear)
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: False)

    result = contenido.publicar_pendientes(limite=1)

    assert publicados == [fisico]
    assert [pid for pid, ok, _ in result] == [fisico]
    assert _estado(fisico) == "publicado"
    assert _estado(sin_stock) == "cancelado"
    assert _estado(externo) == "cancelado"


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


def test_programar_dos_diarias_no_repite_productos():
    _producto("Perfume A", "Perfumes")
    _producto("Celular A", "Celulares")

    assert len(contenido.programar_dos_diarias(dias=2, por_dia=2)) == 2
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


def test_programar_automatico_no_repite_productos():
    _producto("Uno", "Audio")
    _producto("Dos", "Audio")

    assert len(contenido.programar_automatico(dias=5, cantidad_diaria=1)) == 2
    assert contenido.programar_automatico(dias=5, cantidad_diaria=1) == []


def _simular_publicacion(monkeypatch, mensajes):
    monkeypatch.setattr(contenido, "PAUSA_ENTRE_POSTEOS", 0)
    monkeypatch.setattr(contenido, "postear_telegram", lambda p, c=None: (True, "OK"))
    monkeypatch.setattr(contenido.instagram_api, "configurado", lambda: False)
    monkeypatch.setattr(
        contenido.notificaciones,
        "telegram",
        lambda mensaje: (mensajes.append(mensaje), True)[1],
    )


def test_rutina_diaria_avisa_una_vez_al_agotar_catalogo(monkeypatch):
    fisico = _producto("Unico", "Audio")
    _programar(fisico)
    mensajes = []
    _simular_publicacion(monkeypatch, mensajes)

    primera = contenido.rutina_diaria()
    assert primera["agotado"] is True
    assert primera["aviso_agotado"] is True
    assert len(mensajes) == 1
    assert "Catálogo sin pendientes" in mensajes[0]

    segunda = contenido.rutina_diaria()
    assert segunda["agotado"] is True
    assert segunda["aviso_agotado"] is False
    assert segunda["telegram"] is False
    assert segunda["programadas"] == []
    assert len(mensajes) == 1


def test_rutina_diaria_se_reanuda_con_contenido_nuevo(monkeypatch):
    fisico = _producto("Unico", "Audio")
    _programar(fisico)
    mensajes = []
    _simular_publicacion(monkeypatch, mensajes)
    assert contenido.rutina_diaria()["aviso_agotado"] is True

    nuevo = _producto("Nuevo", "Audio")
    tercera = contenido.rutina_diaria()

    assert tercera["agotado"] is False
    assert tercera["aviso_agotado"] is False
    assert [p["producto_id"] for p in tercera["programadas"]] == [nuevo]
    assert len(mensajes) == 2
    assert "Rutina diaria ClickYa" in mensajes[1]
