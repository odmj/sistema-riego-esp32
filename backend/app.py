from flask import Flask, Response, request, jsonify
from datetime import datetime, timedelta
from aemet_service import obtener_prevision_lluvia
from persistence import (
    ahora_utc_iso,
    contar_riegos_del_dia,
    exportar_telemetria_csv,
    finalizar_ultimo_riego,
    guardar_telemetria,
    inicializar_bbdd,
    registrar_inicio_riego,
)
from telegram_service import enviar_alerta_telegram, iniciar_bot_polling

# Inicializamos la aplicación Flask
app = Flask(__name__)
inicializar_bbdd()

# ==============================================================================
# CONFIGURACIÓN AGRONÓMICA Y PARÁMETROS DEL SISTEMA
# ==============================================================================
# Ventanas autorizadas de riego (Formato 24h: inicio inclusivo, fin exclusivo)
VENTANAS_RIEGO = [
    {"inicio": 7,  "fin": 10}, # Ventana Mañana: 07:00 a 09:59
    {"inicio": 21, "fin": 0}   # Ventana Noche:  21:00 a 23:59 (00:00 de mañana marca el fin)
]

HORIZONTE_AEMET_HORAS = 3
INTERVALO_CHEQUEO_RIEGO_MIN = 30

HUMEDAD_CRITICA = 15.0   # Umbral crítico, aplicable dentro de una ventana de riego
HUMEDAD_OBJETIVO = 25.0  # Umbral para riego autónomo normal
DURACION_RIEGO_MIN = 10  # Tiempo que la válvula permanece abierta antes del siguiente despertar

# Variables globales de control
estado_manual_usuario = "AUTONOMO"  # "AUTONOMO", "FORZAR_ABRIR", "FORZAR_CERRAR"
ultimo_estado_valvula = "DESCONOCIDO"
ultima_telemetria = None


# Getters y Setters thread-safe para la comunicación con el bot de Telegram
def obtener_estado_manual():
    return estado_manual_usuario

def establecer_estado_manual(nuevo_estado):
    global estado_manual_usuario
    estado_manual_usuario = nuevo_estado

def obtener_ultima_telemetria():
    return ultima_telemetria.copy() if ultima_telemetria else None


# ==============================================================================
# FUNCIONES AUXILIARES DE TIEMPO Y GESTIÓN DE DEEP SLEEP
# ==============================================================================
def esta_en_ventana_riego(dt_actual):
    """Comprueba si la hora actual cae dentro de alguna ventana configurada."""
    hora = dt_actual.hour
    for v in VENTANAS_RIEGO:
        inicio = v["inicio"]
        fin = v["fin"]
        
        if fin == 0 and inicio > 0:
            if hora >= inicio:
                return True
        else:
            if inicio <= hora < fin:
                return True
    return False

def minutos_hasta_proxima_ventana(dt_actual):
    """Calcula los minutos reales que faltan hasta la siguiente ventana de riego."""
    if esta_en_ventana_riego(dt_actual):
        return INTERVALO_CHEQUEO_RIEGO_MIN

    hora_actual = dt_actual.hour
    
    for v in VENTANAS_RIEGO:
        if hora_actual < v["inicio"]:
            proximo_inicio = dt_actual.replace(hour=v["inicio"], minute=0, second=0, microsecond=0)
            segundos = (proximo_inicio - dt_actual).total_seconds()
            return max(1, int(segundos // 60))
            
    primera_ventana = VENTANAS_RIEGO[0]
    manana = dt_actual + timedelta(days=1)
    proximo_inicio = manana.replace(hour=primera_ventana["inicio"], minute=0, second=0, microsecond=0)
    segundos = (proximo_inicio - dt_actual).total_seconds()
    return max(1, int(segundos // 60))


# ==============================================================================
# ENDPOINT DE TELEMETRÍA
# ==============================================================================
@app.route('/api/v1/telemetria', methods=['POST'])
def recibir_telemetria():
    global estado_manual_usuario, ultimo_estado_valvula, ultima_telemetria
    
    datos = request.get_json()
    print(f"[DEBUG JSON] {datos}")

    if not datos:
        return jsonify({"error": "Payload JSON invalido"}), 400

    ahora = datetime.now()
    hora_actual_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

    humedad = float(datos.get('humedad_suelo_pct', 0))
    bateria = float(datos.get('bateria_v', 0))
    valvula_reportada = datos.get('valvula_estado', 'DESCONOCIDO')

    print(f"\n[{hora_actual_str}] --- TELEMETRÍA RECIBIDA ---")
    print(f"  Dispositivo : {datos.get('dispositivo_id')}")
    print(f"  Ciclo       : #{datos.get('ciclo')}")
    print(f"  Batería     : {bateria} V")
    print(f"  Humedad     : {humedad} %")
    print(f"  Válvula     : {valvula_reportada}")

    respuesta = {}
    minutos_espera = minutos_hasta_proxima_ventana(ahora)
    prevision = None
    en_ventana = esta_en_ventana_riego(ahora)

    # Lógica de Decisión del Backend
    if valvula_reportada == "ABIERTA":
        respuesta = {
            "orden": "CERRADA",
            "motivo": "FIN_DURACION_RIEGO"
        }

    elif estado_manual_usuario == "FORZAR_CERRAR":
        respuesta = {
            "orden": "CERRADA",
            "motivo": "CIERRE_MANUAL_DESDE_TELEGRAM"
        }
        estado_manual_usuario = "AUTONOMO"

    elif estado_manual_usuario == "FORZAR_ABRIR" and en_ventana:
        respuesta = {
            "orden": "ABRIR",
            "motivo": "ORDEN_MANUAL_DESDE_TELEGRAM"
        }
        estado_manual_usuario = "AUTONOMO"  # Una vez atendida, regresamos al modo autónomo

    elif not en_ventana:
        respuesta = {
            "orden": "CERRADA",
            "motivo": f"FUERA_DE_VENTANA_RIEGO (Próxima en {minutos_espera} min)"
        }

    else:
        if humedad < HUMEDAD_CRITICA:
            respuesta = {
                "orden": "ABRIR",
                "motivo": "HUMEDAD_CRITICA_DENTRO_VENTANA_RIEGO"
            }

        elif humedad < HUMEDAD_OBJETIVO:
            prevision = obtener_prevision_lluvia(horizonte_horas=HORIZONTE_AEMET_HORAS)
            va_a_llover = prevision["lluvia_prevista"]
            
            if va_a_llover:
                respuesta = {
                    "orden": "CERRADA",
                    "motivo": f"AHORRO_PREVISION_LLUVIA_AEMET_{HORIZONTE_AEMET_HORAS}H"
                }
            else:
                respuesta = {
                    "orden": "ABRIR",
                    "motivo": "HUMEDAD_BAJA_SIN_LLUVIA"
                }

        else:
            respuesta = {
                "orden": "CERRADA",
                "motivo": "HUMEDAD_SUFICIENTE"
            }

    respuesta["siguiente_ventana_min"] = minutos_espera
    respuesta["duracion_riego_min"] = DURACION_RIEGO_MIN
    orden_final = respuesta["orden"]

    if orden_final == "ABRIR" and valvula_reportada != "ABIERTA":
        registrar_inicio_riego({
            "iniciado_en": ahora_utc_iso(),
            "duracion_programada_min": DURACION_RIEGO_MIN,
            "humedad_inicio_pct": humedad,
            "modo": "MANUAL" if "MANUAL" in respuesta["motivo"] else "AUTONOMO",
            "motivo": respuesta["motivo"],
            "lluvia_prevista": prevision["lluvia_prevista"] if prevision else None,
            "dispositivo_id": datos.get("dispositivo_id", "DESCONOCIDO"),
            "ciclo_inicio": datos.get("ciclo"),
        })
    elif valvula_reportada == "ABIERTA" and orden_final == "CERRADA":
        finalizar_ultimo_riego(humedad, ahora_utc_iso())

    ultima_telemetria = {
        "hora": hora_actual_str,
        "dispositivo": datos.get("dispositivo_id", "DESCONOCIDO"),
        "ciclo": datos.get("ciclo", "DESCONOCIDO"),
        "humedad": humedad,
        "bateria": bateria,
        "valvula": valvula_reportada,
        "orden": orden_final,
        "motivo": respuesta["motivo"],
        "siguiente_ventana_min": minutos_espera,
        "lluvia_mm": prevision["mm_acumulados"] if prevision else None,
        "probabilidad_lluvia": prevision["probabilidad_maxima"] if prevision else None,
    }

    guardar_telemetria({
        "recibido_en": ahora_utc_iso(),
        "dispositivo_id": ultima_telemetria["dispositivo"],
        "ciclo": ultima_telemetria["ciclo"],
        "humedad_suelo_pct": humedad,
        "bateria_v": bateria,
        "valvula_estado_reportado": valvula_reportada,
        "orden_backend": orden_final,
        "motivo_decision": respuesta["motivo"],
        "lluvia_prevista": prevision["lluvia_prevista"] if prevision else None,
        "lluvia_mm_3h": ultima_telemetria["lluvia_mm"],
        "probabilidad_lluvia_pct_3h": ultima_telemetria["probabilidad_lluvia"],
        "siguiente_ventana_min": minutos_espera,
    })

    # --- SENDER OF NOTIFICATIONS TO TELEGRAM ---
    # Notifica si la válvula cambia de estado o ante eventos clave (emergencia / ahorro por lluvia)
    if orden_final != valvula_reportada or "EMERGENCIA" in respuesta["motivo"] or "AHORRO" in respuesta["motivo"]:
        icono = "💧" if orden_final == "ABRIR" else "🔒"
        alerta = (
            f"{icono} *CAMBIO DE ESTADO EN RIEGO*\n"
            f"• *Orden:* `{orden_final}`\n"
            f"• *Motivo:* `{respuesta['motivo']}`\n"
            f"• *Humedad Suelo:* {humedad}%\n"
            f"• *Batería LiFePO4:* {bateria}V\n"
            f"• *Siguiente chequeo:* en {minutos_espera} min"
        )
        enviar_alerta_telegram(alerta)

    ultimo_estado_valvula = orden_final

    print(f"  Respuesta   : {respuesta['orden']} ({respuesta['motivo']})")
    print(f"  Próx.Ventana: dentro de {minutos_espera} minutos")
    print("-------------------------------------------\n")

    return jsonify(respuesta), 200


@app.route('/api/v1/telemetria/export.csv', methods=['GET'])
def exportar_telemetria():
    return Response(
        exportar_telemetria_csv(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=telemetria_riego.csv'
        },
    )


if __name__ == '__main__':
    # Lanzamos el escuchador de comandos de Telegram en un hilo secundario
    iniciar_bot_polling(
        obtener_estado_manual,
        establecer_estado_manual,
        obtener_ultima_telemetria,
        contar_riegos_del_dia,
    )
    
    # Ejecutamos el servidor Flask
    # Evita que el recargador de Flask inicie un segundo polling de Telegram.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)