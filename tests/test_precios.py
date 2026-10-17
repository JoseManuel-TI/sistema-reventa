import precios


def test_calcular_precio_final_margen_sobre_venta():
    params = precios.ParametrosPrecio(costo=1000, margen_deseado=35)
    r = precios.calcular_precio_final(params)
    assert r["precio_final"] == 1538.46
    assert r["ganancia"] == 538.46


def test_calcular_precio_venta_rapido():
    assert precios.calcular_precio_venta_rapido(1000, margen=35) == 1538.46


def test_parametros_parsean_formato_argentino():
    params = precios.ParametrosPrecio(costo="1.000,50", margen_deseado="35%")
    assert params.costo == 1000.5
    assert params.margen_deseado == 35.0


def test_precio_desde_usd(monkeypatch):
    monkeypatch.setattr(precios, "get_dolar_blue", lambda: 1000)
    r = precios.calcular_precio_desde_usd(costo_usd=10, margen=35)
    assert r["costo_ars"] == 10000
    assert r["precio_final"] == 15384.62


def test_precio_sugerido_ml_incluye_comision():
    r = precios.precio_sugerido_ml(costo=1000, comision=20.5)
    # margen ajustado 55.5% -> 1000 / (1 - 0.555)
    assert r["precio_final"] == 2247.19
