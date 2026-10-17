"""Feriados nacionales de Argentina y utilidades para estimar entregas.

La lista se puede editar desde /configuracion (clave FERIADOS). El valor por
defecto corresponde al calendario oficial 2026 (inamovibles, trasladables y
puentes turísticos), fuente: argentina.gob.ar/feriados + Decreto 614/2025.
"""

from datetime import datetime

FERIADOS_2026 = [
    "2026-01-01",  # Año Nuevo
    "2026-02-16",  # Carnaval
    "2026-02-17",  # Carnaval
    "2026-03-23",  # Puente turístico
    "2026-03-24",  # Día Nacional de la Memoria
    "2026-04-02",  # Día del Veterano (Malvinas)
    "2026-04-03",  # Viernes Santo
    "2026-05-01",  # Día del Trabajador
    "2026-05-25",  # Revolución de Mayo
    "2026-06-15",  # Güemes (trasladable)
    "2026-06-20",  # Belgrano
    "2026-07-09",  # Independencia
    "2026-07-10",  # Puente turístico
    "2026-08-17",  # San Martín (trasladable)
    "2026-10-12",  # Diversidad Cultural
    "2026-11-23",  # Soberanía Nacional
    "2026-12-07",  # Puente turístico
    "2026-12-08",  # Inmaculada Concepción
    "2026-12-25",  # Navidad
]

TEXTO_DEFAULT = "\n".join(FERIADOS_2026)


def parsear(texto):
    """Devuelve un set de fechas 'YYYY-MM-DD' desde un texto libre.

    Acepta fechas separadas por saltos de línea, comas o espacios; ignora
    cualquier token con formato inválido.
    """
    fechas = set()
    for parte in (texto or "").replace(",", "\n").replace(";", "\n").split():
        parte = parte.strip()
        if len(parte) != 10 or parte[4] != "-" or parte[7] != "-":
            continue
        try:
            datetime.strptime(parte, "%Y-%m-%d")
        except ValueError:
            continue
        fechas.add(parte)
    return fechas
