from helpers import crear_producto


def _csrf(client):
    with client.session_transaction() as s:
        return s.get("_csrf_token")


def _login(client):
    client.get("/login")
    r = client.post("/login", data={"password": "testpass", "csrf_token": _csrf(client)})
    assert r.status_code == 302
    return client


def test_tienda_publica_responde(client):
    assert client.get("/tienda").status_code == 200


def test_pixel_y_ga_se_inyectan_cuando_configurados(client, monkeypatch):
    import config

    monkeypatch.setattr(config, "_load", lambda: {"META_PIXEL_ID": "1234567890", "GA_MEASUREMENT_ID": "G-TEST123"})
    r = client.get("/tienda")
    assert b"fbq('init', '1234567890')" in r.data
    assert b"G-TEST123" in r.data
    assert b"function trackEvent" in r.data


def test_pixel_no_se_inyecta_si_no_configurado(client):
    r = client.get("/tienda")
    assert b"fbq('init'" not in r.data


def test_login_sin_csrf_es_rechazado(client):
    r = client.post("/login", data={"password": "testpass"})
    assert r.status_code == 400


def test_login_password_incorrecta_no_loguea(client):
    client.get("/login")
    r = client.post("/login", data={"password": "mala", "csrf_token": _csrf(client)})
    assert r.status_code == 200
    with client.session_transaction() as s:
        assert not s.get("admin")


def test_login_correcto_loguea(client):
    _login(client)
    with client.session_transaction() as s:
        assert s.get("admin") is True


def test_admin_requiere_login(client):
    r = client.get("/productos")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_gracias_sin_permiso_no_muestra_pedido(client):
    r = client.get("/gracias/1")
    assert r.status_code == 302


def test_fetch_metadata_bloquea_ssrf(client):
    _login(client)
    r = client.post(
        "/productos/fetch-metadata",
        data={"url": "http://127.0.0.1:8000", "csrf_token": _csrf(client)},
    )
    assert r.status_code == 200
    assert r.get_json().get("error") == "URL no permitida"


def test_checkout_sin_stock_muestra_error(client):
    import db

    pid = crear_producto(stock=5, precio=100)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 3, "csrf_token": _csrf(client)})
    db.update_producto(pid, stock=0)
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "Calle 1",
            "codigo_postal": "1406",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Stock insuficiente" in r.data


def test_checkout_contra_entrega_crea_pedido(client):
    import db

    pid = crear_producto(stock=2, precio=100)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "Calle 1",
            "codigo_postal": "1406",
            "metodo_pago": "contra_entrega",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    pedidos = db.get_pedidos()
    assert len(pedidos) == 1
    assert pedidos[0]["metodo_pago"] == "contra_entrega"
    assert b"Contra entrega" in r.data


def _checkout(client, pid, zona):
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    return client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "Calle 1",
            "codigo_postal": "1406",
            "zona_envio": zona,
        },
        follow_redirects=True,
    )


def test_checkout_cobra_envio_gba(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    r = _checkout(client, pid, "gba")
    assert r.status_code == 200
    pedido = db.get_pedidos()[0]
    assert pedido["zona_envio"] == "gba"
    assert pedido["envio_costo"] == 5500
    assert pedido["total"] == 6500


def test_checkout_caba_cobra_envio(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    _checkout(client, pid, "caba")
    pedido = db.get_pedidos()[0]
    assert pedido["envio_costo"] == 3500
    assert pedido["total"] == 4500


def test_checkout_zona_interior_no_suma_envio(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    _checkout(client, pid, "interior")
    pedido = db.get_pedidos()[0]
    assert pedido["zona_envio"] == "interior"
    assert pedido["envio_costo"] == 0
    assert pedido["total"] == 1000


def test_checkout_zona_invalida_cae_en_caba(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    _checkout(client, pid, "marte")
    pedido = db.get_pedidos()[0]
    assert pedido["zona_envio"] == "caba"
    assert pedido["envio_costo"] == 3500


def test_checkout_guarda_entre_calles_y_localidad(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "Av. Rivadavia 1234",
            "entre_calles": "Sarmiento y Perú",
            "localidad": "Palermo",
            "codigo_postal": "1406",
            "zona_envio": "caba",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    pedido = db.get_pedidos()[0]
    assert pedido["cliente_direccion"] == "Av. Rivadavia 1234"
    assert pedido["cliente_entre_calles"] == "Sarmiento y Perú"
    assert pedido["cliente_localidad"] == "Palermo"
    assert pedido["cliente_codigo_postal"] == "1406"


def test_checkout_sin_direccion_muestra_error(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "",
            "zona_envio": "caba",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"direcci" in r.data.lower()
    assert db.get_pedidos() == []


def test_checkout_sin_telefono_muestra_error(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "",
            "direccion": "Calle 1",
            "zona_envio": "caba",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"tel" in r.data.lower()
    assert db.get_pedidos() == []


def test_checkout_sin_codigo_postal_muestra_error(client):
    import db

    pid = crear_producto(stock=2, precio=1000)
    client.get("/login")
    client.post(f"/carrito/agregar/{pid}", data={"cantidad": 1, "csrf_token": _csrf(client)})
    r = client.post(
        "/checkout/procesar",
        data={
            "csrf_token": _csrf(client),
            "nombre": "Ana",
            "email": "a@b.com",
            "telefono": "11",
            "direccion": "Calle 1",
            "codigo_postal": "",
            "zona_envio": "caba",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"postal" in r.data.lower()
    assert db.get_pedidos() == []


def test_admin_pedido_detalle_render(client):
    import db

    pid = crear_producto(stock=1, precio=100)
    pedido_id = db.crear_pedido(
        "A", "a@b.com", "", "", 0, {"1": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    )
    _login(client)
    assert client.get(f"/pedidos/{pedido_id}").status_code == 200


def test_admin_marcar_cobrado(client):
    import db

    pid = crear_producto(stock=1, precio=100)
    pedido_id = db.crear_pedido(
        "A", "a@b.com", "", "", 0, {"1": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    )
    _login(client)
    r = client.post(
        f"/pedidos/{pedido_id}/cobro",
        data={"csrf_token": _csrf(client), "cobrado": "1", "metodo_cobro": "efectivo"},
    )
    assert r.status_code == 302
    p = db.get_pedido(pedido_id)
    assert p["cobrado"] == 1
    assert p["metodo_cobro"] == "efectivo"


def test_admin_liberar_reserva(client):
    import db

    pid = crear_producto(stock=2, precio=100)
    pedido_id = db.crear_pedido(
        "A", "a@b.com", "", "", 0, {"1": {"producto_id": pid, "cantidad": 2, "nombre": "P"}}
    )
    _login(client)
    r = client.post(f"/pedidos/{pedido_id}/liberar", data={"csrf_token": _csrf(client)})
    assert r.status_code == 302
    assert db.get_producto(pid)["stock"] == 2
    assert db.get_pedido(pedido_id)["estado"] == "cancelado"


def test_contenido_cron_sin_token_rechaza(client):
    assert client.get("/contenido/cron").status_code == 403


def test_contenido_cron_token_incorrecto_rechaza(client, monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")
    r = client.post("/contenido/cron", headers={"X-Cron-Token": "otro"})
    assert r.status_code == 403


def test_contenido_cron_sin_configurar_rechaza(client):
    r = client.get("/contenido/cron?token=secreto")
    assert r.status_code == 403


def test_contenido_cron_token_valido_por_header(client, monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")
    r = client.post("/contenido/cron", headers={"X-Cron-Token": "secreto"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert "publicadas" in data
    assert "pendientes" in data


def test_contenido_cron_token_valido_por_query(client, monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")
    assert client.get("/contenido/cron?token=secreto").status_code == 200


def test_backup_cron_sin_token_rechaza(client):
    assert client.post("/backup/cron").status_code == 403


def test_backup_cron_token_valido_envia_telegram(client, monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "secreto")
    monkeypatch.setattr("web.notificaciones.telegram_documento", lambda path, caption="": True)
    r = client.post("/backup/cron", headers={"X-Cron-Token": "secreto"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["enviado_telegram"] is True


def test_pedidos_filtro_cancelado(client):
    import db

    pid = crear_producto(stock=2, precio=100)
    atendido = db.crear_pedido(
        "A", "a@b.com", "", "", 0, {"1": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    )
    cancelado = db.crear_pedido(
        "B", "b@b.com", "", "", 0, {"2": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    )
    db.actualizar_estado_pedido(cancelado, "cancelado")
    _login(client)
    r = client.get("/pedidos?estado=cancelado")
    assert r.status_code == 200
    assert f'/{cancelado}"'.encode() in r.data
    assert f'/{atendido}"'.encode() not in r.data
