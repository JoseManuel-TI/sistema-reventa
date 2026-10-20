import integraciones as itgr


def test_detectar_plataforma():
    assert itgr.detectar_plataforma("https://www.amazon.com/dp/X") == "amazon"
    assert itgr.detectar_plataforma("https://amzn.to/abc") == "amazon"
    assert itgr.detectar_plataforma("https://es.aliexpress.com/item/1.html") == "aliexpress"
    assert itgr.detectar_plataforma("https://articulo.mercadolibre.com.ar/MLA-1") == "mercadolibre"
    assert itgr.detectar_plataforma("https://hotmart.com/x") == "hotmart"
    assert itgr.detectar_plataforma("https://ejemplo.com") == "otro"


def test_inferir_tipo_producto():
    assert itgr.inferir_tipo_producto("") == "fisico_local"
    assert itgr.inferir_tipo_producto("https://amazon.com/dp/X") == "amazon_affiliate"
    assert itgr.inferir_tipo_producto("https://hotmart.com/x") == "afiliado_digital"


def test_convertir_precio_a_ars():
    assert itgr.convertir_precio_a_ars(10, "USD", dolar_blue=1000) == 10000
    assert itgr.convertir_precio_a_ars(500, "ARS", dolar_blue=1000) == 500


def test_es_externo():
    assert itgr.es_externo("afiliado_digital") is True
    assert itgr.es_externo("amazon_affiliate") is True
    assert itgr.es_externo("fisico_local") is False


def test_producto_url_externa_prefiere_external_url():
    p = {"external_url": "https://a.com", "link_afiliado": "https://b.com"}
    assert itgr.producto_url_externa(p) == "https://a.com"
    assert itgr.producto_url_externa({"link_afiliado": "https://b.com"}) == "https://b.com"
    assert itgr.producto_url_externa({}) is None


def test_url_segura_bloquea_privadas_y_no_http():
    assert itgr._url_segura("http://127.0.0.1/x") is False
    assert itgr._url_segura("http://localhost/x") is False
    assert itgr._url_segura("http://169.254.169.254/latest") is False
    assert itgr._url_segura("http://10.0.0.5/") is False
    assert itgr._url_segura("file:///etc/passwd") is False
    assert itgr._url_segura("ftp://example.com/x") is False
    assert itgr._url_segura("") is False


def test_url_segura_permite_publicas(monkeypatch):
    monkeypatch.setattr(itgr.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])
    assert itgr._url_segura("https://example.com/x") is True


def test_fetch_metadata_bloquea_ssrf():
    r = itgr.fetch_metadata("http://127.0.0.1:8000")
    assert r["ok"] is False
    assert r.get("error") == "URL no permitida"


def test_url_afiliada_amazon_agrega_ascsubtag_sin_romper_query():
    p = {"id": 12, "external_url": "https://www.amazon.com/dp/X?ref_=abc", "plataforma_afiliado": "amazon"}
    url = itgr.url_afiliada(p, "card_cta")
    assert "https://www.amazon.com/dp/X?" in url
    assert "ref_=abc" in url
    assert "ascsubtag=clickya_card_cta_12" in url
    assert url.count("?") == 1


def test_url_afiliada_amazon_no_toca_amzn_to():
    p = {"id": 3, "external_url": "https://amzn.to/xyz", "plataforma_afiliado": "amazon"}
    assert itgr.url_afiliada(p, "bio") == "https://amzn.to/xyz"


def test_url_afiliada_hotmart_usa_src():
    p = {"id": 9, "external_url": "https://go.hotmart.com/A123", "plataforma_afiliado": "hotmart"}
    assert itgr.url_afiliada(p, "telegram") == "https://go.hotmart.com/A123?src=clickya_telegram_9"


def test_url_afiliada_sin_url_devuelve_none():
    assert itgr.url_afiliada({"id": 1}, "web") is None
