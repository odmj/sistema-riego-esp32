import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))
AEMET_API_KEY = os.getenv("AEMET_API_KEY")
CODIGO_MUNICIPIO = "50903"  # Zaragoza
LLUVIA_UTIL_MM = 5.0
PROBABILIDAD_MINIMA_LLUVIA = 75

# Variables globales para la memoria Caché
_cache_prevision = None
_cache_expiracion = None

def obtener_prevision_lluvia(horizonte_horas=3):
    """
    Consulta si hay previsión de lluvia (> 0.5 mm) en las próximas `horizonte_horas`.
    Soporta cruce de medianoche (hoy -> mañana) y memoria caché de 60 minutos.
    """
    global _cache_prevision, _cache_expiracion

    ahora = datetime.now()

    # 1. VERIFICACIÓN DE CACHÉ: Si la consulta tiene menos de 1 hora, usamos el dato en memoria
    if _cache_expiracion and ahora < _cache_expiracion:
        print("[AEMET CACHÉ] Usando predicción almacenada en memoria.")
        return _cache_prevision

    try:
        print(f"[AEMET API] Consultando previsión oficial a AEMET OpenData (Horizonte: {horizonte_horas}h)...")
        
        # Paso 1: Petición del endpoint para obtener la URL del CDN con los datos
        url = f"https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/{CODIGO_MUNICIPIO}"
        headers = {'cache-control': 'no-cache'}
        params = {'api_key': AEMET_API_KEY}

        r1 = requests.get(url, params=params, headers=headers, timeout=5)
        datos_r1 = r1.json()

        if datos_r1.get('estado') != 200:
            print(f"[AEMET ERROR] Respuesta de API no válida: {datos_r1.get('estado')}")
            return False

        # Paso 2: Descarga del JSON real de predicción desde la URL temporal del CDN
        url_datos = datos_r1.get('datos')
        r2 = requests.get(url_datos, timeout=5)
        prediccion = r2.json()

        # Paso 3: Parseo de precipitación y probabilidad dentro del horizonte
        mm_acumulados = 0.0
        probabilidad_maxima = 0
        limite_tiempo = ahora + timedelta(hours=horizonte_horas)

        dias = prediccion[0]['prediccion']['dia']

        # Iteramos sobre los días disponibles (habitualmente hoy [0] y mañana [1])
        for dia_data in dias:
            fecha_base_str = dia_data['fecha'].split('T')[0]  # Extrae "AAAA-MM-DD"

            for p in dia_data.get('precipitacion', []):
                hora_p = int(p['periodo'])
                
                # Construimos el objeto datetime real para la hora evaluada
                fecha_hora_p = datetime.strptime(f"{fecha_base_str} {hora_p:02d}:00", "%Y-%m-%d %H:%M")

                # Comprobamos si la predicción está en el rango [ahora, ahora + horizonte_horas]
                if ahora <= fecha_hora_p <= limite_tiempo:
                    mm_acumulados += float(p.get('value', 0.0))

            for p in dia_data.get('probPrecipitacion', []):
                periodo = p.get('periodo', '')
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
                        probabilidad_maxima, int(p.get('value', 0) or 0)
                    )

        lluvia_detectada = (
            mm_acumulados >= LLUVIA_UTIL_MM
            and probabilidad_maxima >= PROBABILIDAD_MINIMA_LLUVIA
        )
        _cache_prevision = {
            "lluvia_prevista": lluvia_detectada,
            "mm_acumulados": round(mm_acumulados, 2),
            "probabilidad_maxima": probabilidad_maxima,
        }

        # Actualizamos la memoria caché por 60 minutos
        _cache_expiracion = ahora + timedelta(hours=1)
        
        print(f"[AEMET SUCCESS] Previsión próximas {horizonte_horas}h: {_cache_prevision}")
        return _cache_prevision

    except Exception as e:
        print(f"[AEMET ERROR] Excepción durante la consulta: {e}")
        # En caso de fallar la red o la API, devolvemos el último valor en caché o False por seguridad
        return _cache_prevision or {
            "lluvia_prevista": False,
            "mm_acumulados": 0.0,
            "probabilidad_maxima": 0,
        }

def hay_prevision_lluvia(horizonte_horas=3):
    """Compatibilidad: devuelve solo si se cumplen los criterios de lluvia útil."""
    return obtener_prevision_lluvia(horizonte_horas)["lluvia_prevista"]