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


def test_redondear_precios_actuales_conserva_costos_y_omite_afiliados(client):
    import db

    _login(client)
    primero = crear_producto(nombre="Primero", precio=17567, costo=10000)
    segundo = crear_producto(nombre="Segundo", precio=45611, costo=30000)
    tercero = crear_producto(nombre="Tercero", precio=76500, costo=50000)
    cuarto = crear_producto(nombre="Cuarto", precio=76499, costo=50000)
    afiliado = crear_producto(nombre="Afiliado", precio=17567, costo=10000)
    db.update_producto(afiliado, es_afiliado=1)

    r = client.post("/precios/redondear-actuales", data={"csrf_token": _csrf(client)})

    assert r.status_code == 302
    assert db.get_producto(primero)["precio_venta"] == 17600
    assert db.get_producto(segundo)["precio_venta"] == 46000
    assert db.get_producto(tercero)["precio_venta"] == 77000
    assert db.get_producto(cuarto)["precio_venta"] == 76000
    assert db.get_producto(primero)["costo"] == 10000
    assert db.get_producto(afiliado)["precio_venta"] == 17567


def test_calculadoras_de_precios_usen_40_por_defecto(client):
    pid = crear_producto(nombre="Calculadora", costo=1000, precio=1200)
    _login(client)

    pagina = client.get("/precios").data
    assert b'id="margen_deseado" name="margen_deseado" class="form-control" step="0.1" value="40"' in pagina
    assert b'id="margen_todos" name="margen_deseado" class="form-control" step="0.1" value="40"' in pagina
    assert b'value="40"' in client.get(f"/precios/producto/{pid}").data

    r = client.post("/precios", data={"csrf_token": _csrf(client), "costo": "1000"})
    assert r.status_code == 200
    assert b"40.0%" in r.data
    assert b"$ 1.400" in r.data


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


def test_republicar_instagram_route(client, monkeypatch):
    _login(client)
    monkeypatch.setattr("web.cnt.republicar_instagram", lambda base_url="": (2, 0, []))
    r = client.post(
        "/contenido/republicar-instagram",
        data={"csrf_token": _csrf(client)},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"republicado" in r.data


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


def test_dashboard_muestra_invertido_en_stock(client):
    crear_producto(nombre="Inv", stock=3, precio=2500, costo=1000)
    _login(client)

    r = client.get("/dashboard")

    assert r.status_code == 200
    assert b"Venta potencial del stock" in r.data
    assert b"$ 7.500" in r.data
    assert b"Invertido en stock" in r.data
    assert b"$ 3.000" in r.data


def _stat(client, label):
    import re

    html = client.get("/dashboard").data.decode()
    m = re.search(
        r'<div class="label">' + re.escape(label) + r'</div>\s*<div class="value[^"]*">([^<]+)</div>',
        html,
    )
    return m.group(1).strip() if m else None


def test_dashboard_excluye_afiliados_y_muestra_clics(client):
    from helpers import crear_proveedor

    import db

    pid = db.add_producto(
        "Curso afiliado", "", crear_proveedor("Afiliados Amazon"), 0, "Cursos", stock=1,
        es_afiliado=1, link_afiliado="https://amzn.to/x", tipo_producto="amazon_affiliate",
    )
    db.registrar_click_afiliado(pid, "amazon", "https://amzn.to/x")
    _login(client)

    assert _stat(client, "Sin precio asignado") == "0"
    assert _stat(client, "Stock bajo (≤ 3)") == "0"
    assert _stat(client, "Clics afiliados (7 días)") == "1"


def test_api_click_registra_sin_csrf(client):
    from helpers import crear_proveedor

    import db

    pid = db.add_producto(
        "SSD afiliado", "", crear_proveedor("Afiliados"), 0, "Tecnología", stock=0,
        es_afiliado=1, link_afiliado="https://www.amazon.com/dp/X", tipo_producto="amazon_affiliate",
        publicar=1,
    )
    r = client.post(f"/api/click/{pid}", json={"src": "web_card_cta"})
    assert r.status_code == 204
    stats = db.get_clicks_afiliados_resumen()
    assert stats["total"] == 1


def test_api_click_rechaza_producto_local(client):
    pid = crear_producto()
    assert client.post(f"/api/click/{pid}", json={"src": "x"}).status_code == 404


def test_card_afiliada_usa_link_directo_y_divulga(client):
    from helpers import crear_proveedor

    import db

    db.add_producto(
        "SSD afiliado", "", crear_proveedor("Afiliados"), 0, "Tecnología", stock=0,
        es_afiliado=1, link_afiliado="https://www.amazon.com/dp/X", tipo_producto="amazon_affiliate",
        publicar=1,
    )
    html = client.get("/tienda").data.decode()
    assert "ascsubtag=clickya_web_card_cta_" in html
    assert "Enlace de afiliado" in html
    assert "/out/" not in html


def test_detalle_hotmart_link_directo_y_divulgacion(client):
    from helpers import crear_proveedor

    import db

    pid = db.add_producto(
        "Curso de ventas", "", crear_proveedor("Hotmart"), 0, "Cursos", stock=0,
        es_afiliado=1, link_afiliado="https://go.hotmart.com/A123", plataforma_afiliado="hotmart",
        tipo_producto="afiliado_digital", publicar=1,
    )
    html = client.get(f"/tienda/{pid}").data.decode()
    assert f"https://go.hotmart.com/A123?src=clickya_web_detail_{pid}" in html
    assert "Enlace de afiliado" in html
    assert "ClickYa no procesa este pago" in html


def test_seleccion_publica_muestra_productos_en_orden(client):
    from helpers import crear_proveedor

    import db

    prov = crear_proveedor("Sel")
    p1 = db.add_producto("Primero", "", prov, 0, "Tecnología", stock=2, publicar=1,
                         es_afiliado=1, link_afiliado="https://www.amazon.com/dp/A",
                         tipo_producto="amazon_affiliate")
    p2 = db.add_producto("Segundo", "", prov, 0, "Tecnología", stock=2, publicar=1,
                         es_afiliado=1, link_afiliado="https://www.amazon.com/dp/B",
                         tipo_producto="amazon_affiliate")
    sid = db.add_seleccion("kit-viaje", "Kit para viajar", "Los imprescindibles")
    db.set_seleccion_items(sid, [p2, p1])

    html = client.get("/coleccion/kit-viaje").data.decode()
    assert html.index("Segundo") < html.index("Primero")
    assert "Enlace de afiliado" in html


def test_seleccion_inactiva_o_inexistente_da_404(client):
    import db

    sid = db.add_seleccion("borrador", "Borrador", "", activo=0)
    assert client.get("/coleccion/borrador").status_code == 404
    assert client.get("/coleccion/no-existe").status_code == 404
    assert sid


def test_admin_crea_y_edita_seleccion(client):
    from helpers import crear_proveedor

    import db

    _login(client)
    pid = db.add_producto("Elegido", "", crear_proveedor("Sel"), 0, "Cursos", stock=0,
                          publicar=1, es_afiliado=1, link_afiliado="https://go.hotmart.com/A1",
                          plataforma_afiliado="hotmart", tipo_producto="afiliado_digital")
    r = client.post("/selecciones", data={
        "titulo": "Cursos de IA", "slug": "cursos-ia", "descripcion": "Para arrancar",
        "activo": "on", "csrf_token": _csrf(client),
    })
    assert r.status_code == 302
    sel = db.get_seleccion_por_slug("cursos-ia")
    assert sel and sel["titulo"] == "Cursos de IA"

    r = client.post(f"/selecciones/{sel['id']}", data={
        "titulo": "Cursos de IA", "slug": "cursos-ia", "descripcion": "Actualizado",
        "activo": "on", f"incluir_{pid}": "on", f"orden_{pid}": "1",
        "csrf_token": _csrf(client),
    })
    assert r.status_code == 302
    items = db.get_seleccion_items(sel["id"])
    assert [p["id"] for p in items] == [pid]


def test_comisiones_dashboard_y_afiliados(client):
    from datetime import datetime

    import db

    db.add_comision(datetime.now().strftime("%Y-%m"), "amazon", 10.0, 2.5)
    _login(client)
    html = client.get("/contenido/afiliados").data.decode()
    assert "Comisiones por mes" in html
    assert "7.50" in html
    assert "US$ 7.50" in client.get("/dashboard").data.decode()


def test_manual_instagram_usa_url_corta_valida(client):
    pid = crear_producto()
    _login(client)
    html = client.get(f"/contenido/manual/{pid}").data.decode()
    assert f"/tienda/{pid}" in html
    assert "/tienda/producto/" not in html


def test_cancelar_publicacion_puntual(client):
    import contenido as cnt

    pid = crear_producto()
    pub_id = cnt.programar_publicacion(pid, "2030-01-01 12:00:00")
    _login(client)

    r = client.post(f"/contenido/publicacion/{pub_id}/cancelar", data={"csrf_token": _csrf(client)})
    assert r.status_code == 302
    pub = next(p for p in cnt.listar_publicaciones(50) if p["id"] == pub_id)
    assert pub["estado"] == "cancelado"
