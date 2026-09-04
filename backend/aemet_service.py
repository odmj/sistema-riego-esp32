import requests
from datetime import datetime, timedelta

AEMET_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvbGxlcm9zZG0uakBnbWFpbC5jb20iLCJqdGkiOiIyZjEzNGQzYi05NzI1LTQzZWQtYjYzZi02ZjI5Y2Y1MDdhMzAiLCJleHAiOjE3OTcxMDg4ODUsImlzcyI6IkFFTUVUIiwiaWF0IjoxNzg4NDY4ODg1LCJ1c2VySWQiOiIyZjEzNGQzYi05NzI1LTQzZWQtYjYzZi02ZjI5Y2Y1MDdhMzAiLCJyb2xlIjoiIn0.8FUPUZqIdxZlsOpn19ZAJeY10AEupY8H3bR0T9IAXEg"
CODIGO_MUNICIPIO = "50903"  # Zaragoza

# Variables globales para la memoria Caché
_cache_lluvia = False
_cache_expiracion = None

def hay_prevision_lluvia(horizonte_horas=4):
    """
    Consulta si hay previsión de lluvia (> 0.5 mm) en las próximas `horizonte_horas`.
    Soporta cruce de medianoche (hoy -> mañana) y memoria caché de 60 minutos.
    """
    global _cache_lluvia, _cache_expiracion

    ahora = datetime.now()

    # 1. VERIFICACIÓN DE CACHÉ: Si la consulta tiene menos de 1 hora, usamos el dato en memoria
    if _cache_expiracion and ahora < _cache_expiracion:
        print("[AEMET CACHÉ] Usando predicción almacenada en memoria.")
        return _cache_lluvia

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

        # Paso 3: Parseo robusto de la estructura interna cruzando días
        lluvia_detectada = False
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
                    valor_precipitacion = float(p.get('value', 0.0))
                    if valor_precipitacion > 0.5:  # Umbral de lluvia útil (> 0.5 mm)
                        lluvia_detectada = True
                        break

            if lluvia_detectada:
                break

        # Actualizamos la memoria caché por 60 minutos
        _cache_lluvia = lluvia_detectada
        _cache_expiracion = ahora + timedelta(hours=1)
        
        print(f"[AEMET SUCCESS] Lluvia detectada en las próximas {horizonte_horas}h: {lluvia_detectada}")
        return _cache_lluvia

    except Exception as e:
        print(f"[AEMET ERROR] Excepción durante la consulta: {e}")
        # En caso de fallar la red o la API, devolvemos el último valor en caché o False por seguridad
        return _cache_lluvia