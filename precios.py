"""
Calculadora de precios — margen sobre el costo (markup).
Precio final = costo * (1 + margen/100)
Precio desde USD = (costo_usd * dolar_blue) * (1 + margen/100)
"""

import math
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import config

_DOLAR_CACHE = {"valor": None, "ts": 0.0}
_DOLAR_TTL = 3600  # segundos: refrescamos la cotización como mucho 1 vez por hora


def redondear_precio_venta(precio: float) -> float:
    """Redondea a centenas bajo $20.000 y a miles desde $20.000."""
    if precio <= 0:
        return 0.0
    monto = Decimal(str(precio))
    escala = Decimal("1000") if monto >= 20000 else Decimal("100")
    redondeado = (monto / escala).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * escala
    return float(max(Decimal("100"), redondeado))


def get_dolar_blue():
    """Cotización del dólar blue, cacheada en memoria por 1 hora.

    Evita pegarle a la API y reescribir config.json en cada request.
    """
    ahora = time.time()
    if _DOLAR_CACHE["valor"] and (ahora - _DOLAR_CACHE["ts"]) < _DOLAR_TTL:
        return _DOLAR_CACHE["valor"]

    # Intentamos obtener la cotización en tiempo real desde dolarapi.com
    import json
    import urllib.request
    try:
        url = "https://dolarapi.com/v1/dolares/blue"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            cotizacion = float(data.get("venta"))
            if cotizacion > 0:
                if str(config.get("DOLAR_BLUE")) != str(cotizacion):
                    config.set("DOLAR_BLUE", cotizacion)
                _DOLAR_CACHE.update(valor=cotizacion, ts=ahora)
                return cotizacion
    except Exception:
        pass

    # Fallback a la configuración guardada o por defecto de seguridad
    try:
        valor = float(config.get("DOLAR_BLUE"))
    except (ValueError, TypeError):
        valor = 1510
    _DOLAR_CACHE.update(valor=valor, ts=ahora)
    return valor


@dataclass
class ParametrosPrecio:
    costo: float
    margen_deseado: float = 40.0

    def __post_init__(self):
        for field_name in self.__dataclass_fields__:
            val = getattr(self, field_name)
            if isinstance(val, str):
                cleaned = val.replace("%", "").replace("$", "").replace(" ", "").strip()
                if "," in cleaned:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                setattr(self, field_name, float(cleaned))
        if not math.isfinite(self.costo) or self.costo < 0:
            raise ValueError("El costo debe ser un número positivo.")
        if not math.isfinite(self.margen_deseado) or not 0 <= self.margen_deseado <= 1000:
            raise ValueError("El margen debe estar entre 0 y 1000.")


def calcular_precio_final(params: ParametrosPrecio) -> dict:
    costo = params.costo
    margen = params.margen_deseado

    precio_final = redondear_precio_venta(costo * (1 + margen / 100))
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


def calcular_precio_desde_usd(costo_usd: float, margen: float = 40) -> dict:
    dolar = get_dolar_blue()
    costo_ars = round(costo_usd * dolar, 2)
    params = ParametrosPrecio(costo=costo_ars, margen_deseado=margen)
    resultado = calcular_precio_final(params)
    resultado["costo_usd"] = costo_usd
    resultado["dolar_blue"] = dolar
    resultado["costo_ars"] = costo_ars
    return resultado


def calcular_precio_venta_rapido(costo: float, margen: float = 40) -> float:
    return calcular_precio_final(ParametrosPrecio(costo, margen))["precio_final"]


def precio_sugerido_ml(costo: float, comision: float = 20.5) -> dict:
    """Precio para Mercado Libre que, tras la comisión, deja un markup del 40%."""
    margen = 40.0
    base = costo * (1 + margen / 100)
    precio_final = redondear_precio_venta(base / (1 - comision / 100))
    return {
        "costo": round(costo, 2),
        "precio_final": precio_final,
        "ganancia": round(precio_final - costo, 2),
        "margen_porcentaje": margen,
        "comision_ml": comision,
        "params_usados": {"costo": costo, "margen_deseado": margen, "comision": comision},
    }
