import precios


def test_calcular_precio_final_margen_sobre_costo():
    params = precios.ParametrosPrecio(costo=1000, margen_deseado=35)
    r = precios.calcular_precio_final(params)
    assert r["precio_final"] == 1400.00
    assert r["ganancia"] == 400.00


def test_calcular_precio_venta_rapido():
    assert precios.calcular_precio_venta_rapido(1000, margen=35) == 1400.00


def test_redondeo_precio_venta_a_centenas():
    assert precios.redondear_precio_venta(17567) == 17600
    assert precios.redondear_precio_venta(45611) == 45600
    assert precios.redondear_precio_venta(17550) == 17600
    assert precios.redondear_precio_venta(20) == 100


def test_parametros_parsean_formato_argentino():
    params = precios.ParametrosPrecio(costo="1.000,50", margen_deseado="35%")
    assert params.costo == 1000.5
    assert params.margen_deseado == 35.0


def test_precio_desde_usd(monkeypatch):
    monkeypatch.setattr(precios, "get_dolar_blue", lambda: 1000)
    r = precios.calcular_precio_desde_usd(costo_usd=10, margen=35)
    assert r["costo_ars"] == 10000
    assert r["precio_final"] == 13500.00


def test_precio_sugerido_ml_incluye_comision():
    r = precios.precio_sugerido_ml(costo=1000, comision=20.5)
    # markup 35% sobre el costo, cubriendo la comisión de ML
    # 1000 * 1.35 = 1350 ; 1350 / (1 - 0.205) = 1698.11, redondeado a centenas
    assert r["precio_final"] == 1700.00
