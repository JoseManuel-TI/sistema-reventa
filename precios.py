"""
Calculadora de precios — markup simple sobre costo.
Precio final = costo * (1 + margen/100)
"""

from dataclasses import dataclass


@dataclass
class ParametrosPrecio:
    costo: float
    margen_deseado: float = 35.0

    def __post_init__(self):
        for field_name in self.__dataclass_fields__:
            val = getattr(self, field_name)
            if isinstance(val, str):
                cleaned = val.replace("%", "").replace("$", "").replace(",", ".").strip()
                setattr(self, field_name, float(cleaned))


def calcular_precio_final(params: ParametrosPrecio) -> dict:
    costo = params.costo
    margen = params.margen_deseado

    precio_final = round(costo * (1 + margen / 100), 2)
    ganancia = round(precio_final - costo, 2)
    margen_porcentaje = round(ganancia / costo * 100, 1) if costo else 0

    desglose = {
        "costo": round(costo, 2),
        "precio_final": precio_final,
        "ganancia": ganancia,
        "margen_porcentaje": margen_porcentaje,
        "params_usados": {
            "costo": costo,
            "margen_deseado": margen,
        },
    }
    return desglose


def calcular_precio_venta_rapido(costo: float, margen: float = 35) -> float:
    return round(costo * (1 + margen / 100), 2)


def precio_sugerido_ml(costo: float, comision: float = 20.5) -> dict:
    """
    Calcula precio sugerido para Mercado Libre considerando su comisión.
    """
    margen_ajustado = 35 + comision
    params = ParametrosPrecio(costo=costo, margen_deseado=margen_ajustado)
    return calcular_precio_final(params)
