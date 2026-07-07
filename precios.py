"""
Calculadora de precios — margen sobre precio de venta.
Precio final = costo / (1 - margen/100)
Precio desde USD = (costo_usd * dolar_blue) / (1 - margen/100)
"""

from dataclasses import dataclass

import config


def get_dolar_blue():
    # Intentamos obtener la cotización en tiempo real desde la API libre de dolarapi.com
    import urllib.request
    import json
    try:
        url = "https://dolarapi.com/v1/dolares/blue"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            cotizacion = float(data.get("venta"))
            if cotizacion > 0:
                # Actualizamos de forma silenciosa la configuración persistente
                config.set("DOLAR_BLUE", cotizacion)
                return cotizacion
    except Exception:
        pass

    # Fallback a la configuración guardada o por defecto de seguridad
    try:
        return float(config.get("DOLAR_BLUE"))
    except (ValueError, TypeError):
        return 1510


@dataclass
class ParametrosPrecio:
    costo: float
    margen_deseado: float = 35.0

    def __post_init__(self):
        for field_name in self.__dataclass_fields__:
            val = getattr(self, field_name)
            if isinstance(val, str):
                cleaned = val.replace("%", "").replace("$", "").replace(" ", "").strip()
                if "," in cleaned:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                setattr(self, field_name, float(cleaned))


def calcular_precio_final(params: ParametrosPrecio) -> dict:
    costo = params.costo
    margen = params.margen_deseado

    precio_final = round(costo / (1 - margen / 100), 2)
    ganancia = round(precio_final - costo, 2)

    desglose = {
        "costo": round(costo, 2),
        "precio_final": precio_final,
        "ganancia": ganancia,
        "margen_porcentaje": margen,
        "params_usados": {
            "costo": costo,
            "margen_deseado": margen,
        },
    }
    return desglose


def calcular_precio_desde_usd(costo_usd: float, margen: float = 35) -> dict:
    dolar = get_dolar_blue()
    costo_ars = round(costo_usd * dolar, 2)
    params = ParametrosPrecio(costo=costo_ars, margen_deseado=margen)
    resultado = calcular_precio_final(params)
    resultado["costo_usd"] = costo_usd
    resultado["dolar_blue"] = dolar
    resultado["costo_ars"] = costo_ars
    return resultado


def calcular_precio_venta_rapido(costo: float, margen: float = 35) -> float:
    return round(costo / (1 - margen / 100), 2)


def precio_sugerido_ml(costo: float, comision: float = 20.5) -> dict:
    """
    Calcula precio sugerido para Mercado Libre considerando su comisión.
    """
    margen_ajustado = 35 + comision
    params = ParametrosPrecio(costo=costo, margen_deseado=margen_ajustado)
    return calcular_precio_final(params)
