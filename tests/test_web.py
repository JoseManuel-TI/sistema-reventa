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
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Stock insuficiente" in r.data
