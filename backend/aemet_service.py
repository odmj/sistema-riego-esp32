"""
Servicio de consulta a AEMET OpenData.

Consulta la predicción horaria oficial para el municipio configurado y
determina si se espera "lluvia útil" en el horizonte temporal indicado
(por defecto, 3 horas).

Criterios de "lluvia útil":
  - Precipitación acumulada >= LLUVIA_UTIL_MM (5 mm)
  - Probabilidad máxima >= PROBABILIDAD_MINIMA_LLUVIA (75%)

Implementa caché en memoria (60 min) protegida con Lock para ser
thread-safe. Si AEMET falla, devuelve el último valor cacheado o un
valor conservador (sin lluvia → regar).
"""

import logging
import os
import threading
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

AEMET_API_KEY = os.getenv("AEMET_API_KEY")
CODIGO_MUNICIPIO = "50903"  # Zaragoza
LLUVIA_UTIL_MM = 5.0
PROBABILIDAD_MINIMA_LLUVIA = 75
TIMEOUT_AEMET_S = 5
CACHE_TTL_MIN = 60

if not AEMET_API_KEY:
    logger.warning(
        "AEMET_API_KEY no configurada en .env. Las consultas a AEMET fallarán."
    )

# Estado de caché protegido con Lock
_cache_lock = threading.Lock()
_cache_prevision = None
_cache_expiracion = None

_RESPUESTA_SEGURA = {
    "lluvia_prevista": False,
    "mm_acumulados": 0.0,
    "probabilidad_maxima": 0,
}


def _leer_cache_si_valida():
    """Devuelve la caché si sigue vigente, o None. Thread-safe."""
    with _cache_lock:
        if _cache_expiracion and datetime.now() < _cache_expiracion:
            return _cache_prevision
        return None


def _actualizar_cache(valor):
    """Actualiza la caché con un nuevo valor y renueva la expiración."""
    global _cache_prevision, _cache_expiracion
    with _cache_lock:
        _cache_prevision = valor
        _cache_expiracion = datetime.now() + timedelta(minutes=CACHE_TTL_MIN)


def _respuesta_cache_o_segura():
    """Devuelve la caché vigente o un valor conservador (sin lluvia)."""
    with _cache_lock:
        return _cache_prevision or _RESPUESTA_SEGURA


def _consultar_aemet(horizonte_horas):
    """
    Realiza la consulta real a AEMET y devuelve el dict con la previsión.
    Lanza excepción si algo falla (red, JSON, API).
    """
    url = (
        "https://opendata.aemet.es/opendata/api/prediccion/"
        f"especifica/municipio/horaria/{CODIGO_MUNICIPIO}"
    )
    headers = {"cache-control": "no-cache"}
    params = {"api_key": AEMET_API_KEY}

    logger.info(
        f"Consultando AEMET (horizonte={horizonte_horas}h, municipio={CODIGO_MUNICIPIO})"
    )

    # Paso 1: petición inicial para obtener la URL del CDN
    r1 = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_AEMET_S)
    datos_r1 = r1.json()

    if datos_r1.get("estado") != 200:
        raise RuntimeError(
            f"AEMET devolvió estado {datos_r1.get('estado')}: "
            f"{datos_r1.get('descripcion', 'sin descripción')}"
        )

    # Paso 2: descarga del JSON real desde la URL temporal
    url_datos = datos_r1.get("datos")
    if not url_datos:
        raise RuntimeError("AEMET no devolvió URL de datos")

    r2 = requests.get(url_datos, timeout=TIMEOUT_AEMET_S)
    prediccion = r2.json()

    # Paso 3: parseo de precipitación y probabilidad en el horizonte
    ahora = datetime.now()
    limite_tiempo = ahora + timedelta(hours=horizonte_horas)

    mm_acumulados = 0.0
    probabilidad_maxima = 0

    dias = prediccion[0]["prediccion"]["dia"]
    for dia_data in dias:
        fecha_base_str = dia_data["fecha"].split("T")[0]

        for p in dia_data.get("precipitacion", []):
            hora_p = int(p["periodo"])
            fecha_hora_p = datetime.strptime(
                f"{fecha_base_str} {hora_p:02d}:00", "%Y-%m-%d %H:%M"
            )
            if ahora <= fecha_hora_p <= limite_tiempo:
                mm_acumulados += float(p.get("value", 0.0))

        for p in dia_data.get("probPrecipitacion", []):
            periodo = p.get("periodo", "")
            if len(periodo) != 4:
                continue
            inicio = int(periodo[:2])
            fin = int(periodo[2:])
            inicio_periodo = datetime.strptime(
                f"{fecha_base_str} {inicio:02d}:00", "%Y-%m-%d %H:%M"
            )
            fin_periodo = datetime.strptime(
                f"{fecha_base_str} {fin:02d}:00", "%Y-%m-%d %H:%M"
            )
            if fin <= inicio:
                fin_periodo += timedelta(days=1)
            if inicio_periodo <= limite_tiempo and fin_periodo >= ahora:
                probabilidad_maxima = max(
                    probabilidad_maxima, int(p.get("value", 0) or 0)
                )

    lluvia_detectada = (
        mm_acumulados >= LLUVIA_UTIL_MM
        and probabilidad_maxima >= PROBABILIDAD_MINIMA_LLUVIA
    )

    resultado = {
        "lluvia_prevista": lluvia_detectada,
        "mm_acumulados": round(mm_acumulados, 2),
        "probabilidad_maxima": probabilidad_maxima,
    }
    logger.info(f"AEMET OK | {resultado}")
    return resultado


def obtener_prevision_lluvia(horizonte_horas=3):
    """
    Devuelve la previsión de lluvia para las próximas `horizonte_horas`.
    Usa caché de 60 min. Si AEMET falla, devuelve el último valor cacheado
    o, en su defecto, "sin lluvia" (política conservadora: regar).
    """
    cache = _leer_cache_si_valida()
    if cache is not None:
        logger.debug("AEMET caché vigente, devolviendo valor almacenado")
        return cache

    try:
        resultado = _consultar_aemet(horizonte_horas)
        _actualizar_cache(resultado)
        return resultado
    except Exception as e:
        logger.error(f"AEMET no disponible: {e}. Usando caché o valor conservador.")
        return _respuesta_cache_o_segura()