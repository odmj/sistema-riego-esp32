"""
Backend del sistema de riego autónomo.
Recibe telemetría del ESP32, decide la orden de riego combinando
ventanas horarias, humedad del suelo y previsión de AEMET,
y notifica por Telegram.
"""

import logging
import os
import threading
from datetime import datetime, timedelta

from flask import Flask, Response, request, jsonify

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


# ==============================================================================
# CONFIGURACIÓN DE LOGGING
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("flask.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ==============================================================================
# INICIALIZACIÓN
# ==============================================================================
app = Flask(__name__)
inicializar_bbdd()


# ==============================================================================
# CONFIGURACIÓN AGRONÓMICA Y PARÁMETROS DEL SISTEMA
# ==============================================================================
# Ventanas autorizadas de riego (Formato 24h: inicio inclusivo, fin exclusivo)
VENTANAS_RIEGO = [
    {"inicio": 7,  "fin": 10},  # Ventana Mañana: 07:00 a 09:59
    {"inicio": 21, "fin": 0},   # Ventana Noche:  21:00 a 23:59
]

HORIZONTE_AEMET_HORAS = 3
INTERVALO_CHEQUEO_RIEGO_MIN = 30

HUMEDAD_CRITICA = 15.0   # Umbral crítico, aplicable dentro de una ventana de riego
HUMEDAD_OBJETIVO = 25.0  # Umbral para riego autónomo normal
DURACION_RIEGO_MIN = 10  # Minutos de riego antes del siguiente despertar

# Caducidad de comandos manuales (evita comandos zombis)
CADUCIDAD_COMANDO_MANUAL_HORAS = 12


# ==============================================================================
# ESTADO GLOBAL THREAD-SAFE
# ==============================================================================
# El estado es compartido entre el hilo de Flask (telemetría) y el hilo del
# bot de Telegram (comandos manuales). Se protege con un Lock para garantizar
# consistencia en operaciones compuestas.
_estado_lock = threading.Lock()

_estado_manual = {
    "modo": "AUTONOMO",        # "AUTONOMO" | "FORZAR_ABRIR" | "FORZAR_CERRAR"
    "timestamp": None,         # datetime del momento en que se emitió
}
_ultima_telemetria = None
_ultimo_estado_valvula = "DESCONOCIDO"


def obtener_estado_manual():
    """Devuelve el modo manual actual (thread-safe)."""
    with _estado_lock:
        return _estado_manual["modo"]


def establecer_estado_manual(nuevo_estado):
    """
    Establece un nuevo modo manual.
    Registra el timestamp para permitir caducidad.
    """
    with _estado_lock:
        _estado_manual["modo"] = nuevo_estado
        _estado_manual["timestamp"] = datetime.now() if nuevo_estado != "AUTONOMO" else None
    logger.info(f"Modo manual establecido a: {nuevo_estado}")


def obtener_ultima_telemetria():
    """Devuelve una copia de la última telemetría (thread-safe)."""
    with _estado_lock:
        return _ultima_telemetria.copy() if _ultima_telemetria else None


def _comando_manual_caducado():
    """
    Comprueba si el comando manual actual ha caducado.
    Debe llamarse SIEMPRE dentro del lock.
    """
    if _estado_manual["modo"] == "AUTONOMO":
        return False
    if _estado_manual["timestamp"] is None:
        return False
    delta = datetime.now() - _estado_manual["timestamp"]
    return delta > timedelta(hours=CADUCIDAD_COMANDO_MANUAL_HORAS)


def _resetear_estado_manual():
    """Resetea el modo manual a AUTONOMO. Debe llamarse dentro del lock."""
    _estado_manual["modo"] = "AUTONOMO"
    _estado_manual["timestamp"] = None


# ==============================================================================
# FUNCIONES AUXILIARES DE TIEMPO
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
            proximo_inicio = dt_actual.replace(
                hour=v["inicio"], minute=0, second=0, microsecond=0
            )
            segundos = (proximo_inicio - dt_actual).total_seconds()
            return max(1, int(segundos // 60))

    primera_ventana = VENTANAS_RIEGO[0]
    manana = dt_actual + timedelta(days=1)
    proximo_inicio = manana.replace(
        hour=primera_ventana["inicio"], minute=0, second=0, microsecond=0
    )
    segundos = (proximo_inicio - dt_actual).total_seconds()
    return max(1, int(segundos // 60))


# ==============================================================================
# LÓGICA DE DECISIÓN
# ==============================================================================
def decidir_orden(datos, ahora):
    """
    Decide la orden a devolver al ESP32 combinando las capas de decisión.

    Orden de prioridad:
      1. Fin de riego (si la válvula está abierta, cerrar).
      2. Comando manual de cierre.
      3. Comando manual de apertura (con caducidad y ventana).
      4. Fuera de ventana de riego.
      5. Humedad crítica.
      6. Humedad baja con/sin previsión de lluvia.
      7. Humedad suficiente.

    Devuelve (respuesta_dict, prevision_dict_o_None).
    """
    humedad = float(datos.get("humedad_suelo_pct", 0))
    valvula_reportada = datos.get("valvula_estado", "DESCONOCIDO")

    en_ventana = esta_en_ventana_riego(ahora)
    minutos_espera = minutos_hasta_proxima_ventana(ahora)

    prevision = None

    # --- Capa 1: fin de riego ---
    if valvula_reportada == "ABIERTA":
        return _construir_respuesta("CERRADA", "FIN_DURACION_RIEGO", minutos_espera), None

    # --- Capas 2-3: comandos manuales ---
    with _estado_lock:
        modo = _estado_manual["modo"]
        caducado = _comando_manual_caducado()

        if modo == "FORZAR_CERRAR":
            _resetear_estado_manual()
            return _construir_respuesta(
                "CERRADA", "CIERRE_MANUAL_DESDE_TELEGRAM", minutos_espera
            ), None

        if modo == "FORZAR_ABRIR":
            if caducado:
                _resetear_estado_manual()
                return _construir_respuesta(
                    "CERRADA", "COMANDO_MANUAL_CADUCADO", minutos_espera
                ), None
            if en_ventana:
                _resetear_estado_manual()
                return _construir_respuesta(
                    "ABRIR", "ORDEN_MANUAL_DESDE_TELEGRAM", minutos_espera
                ), None
            # Comando pendiente: sigue vivo pero esperando ventana
            return _construir_respuesta(
                "CERRADA", "ESPERANDO_VENTANA_PARA_ORDEN_MANUAL", minutos_espera
            ), None

    # --- Capa 4: fuera de ventana ---
    if not en_ventana:
        return _construir_respuesta(
            "CERRADA", "FUERA_DE_VENTANA_RIEGO", minutos_espera
        ), None

    # --- Capa 5: humedad crítica ---
    if humedad < HUMEDAD_CRITICA:
        return _construir_respuesta(
            "ABRIR", "HUMEDAD_CRITICA_DENTRO_VENTANA_RIEGO", minutos_espera
        ), None

    # --- Capa 6: humedad baja, consultar AEMET ---
    if humedad < HUMEDAD_OBJETIVO:
        prevision = obtener_prevision_lluvia(horizonte_horas=HORIZONTE_AEMET_HORAS)
        if prevision["lluvia_prevista"]:
            return _construir_respuesta(
                "CERRADA",
                "AHORRO_PREVISION_LLUVIA_AEMET",
                minutos_espera,
            ), prevision
        return _construir_respuesta(
            "ABRIR", "HUMEDAD_BAJA_SIN_LLUVIA", minutos_espera
        ), prevision

    # --- Capa 7: humedad suficiente ---
    return _construir_respuesta(
        "CERRADA", "HUMEDAD_SUFICIENTE", minutos_espera
    ), None


def _construir_respuesta(orden, motivo, minutos_espera):
    """
    Construye el dict de respuesta con separación entre motivo (enum limpio)
    y detalle (texto humano). El firmware solo necesita 'orden', 'motivo',
    'siguiente_ventana_min' y 'duracion_riego_min'.
    """
    return {
        "orden": orden,
        "motivo": motivo,
        "siguiente_ventana_min": minutos_espera,
        "duracion_riego_min": DURACION_RIEGO_MIN,
    }


# ==============================================================================
# ENDPOINT DE TELEMETRÍA
# ==============================================================================
@app.route("/api/v1/telemetria", methods=["POST"])
def recibir_telemetria():
    global _ultima_telemetria, _ultimo_estado_valvula

    # --- Validación del payload ---
    datos = request.get_json(silent=True)
    if not datos:
        logger.warning("Payload JSON inválido o vacío")
        return jsonify({"error": "Payload JSON inválido"}), 400

    try:
        humedad = float(datos.get("humedad_suelo_pct", 0))
        bateria = float(datos.get("bateria_v", 0))
    except (ValueError, TypeError) as e:
        logger.error(f"Error parseando telemetría: {e} | datos={datos}")
        return jsonify({"error": "Valores numéricos inválidos"}), 400

    valvula_reportada = datos.get("valvula_estado", "DESCONOCIDO")
    ahora = datetime.now()

    logger.info(
        f"Telemetría recibida | dispositivo={datos.get('dispositivo_id')} "
        f"ciclo=#{datos.get('ciclo')} humedad={humedad}% bateria={bateria}V "
        f"valvula={valvula_reportada}"
    )

    # --- Decisión ---
    respuesta, prevision = decidir_orden(datos, ahora)
    orden_final = respuesta["orden"]
    minutos_espera = respuesta["siguiente_ventana_min"]

    # --- Persistencia de eventos de riego ---
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

    # --- Construcción del registro de telemetría ---
    registro = {
        "hora": ahora.strftime("%Y-%m-%d %H:%M:%S"),
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
        "dispositivo_id": registro["dispositivo"],
        "ciclo": registro["ciclo"],
        "humedad_suelo_pct": humedad,
        "bateria_v": bateria,
        "valvula_estado_reportado": valvula_reportada,
        "orden_backend": orden_final,
        "motivo_decision": respuesta["motivo"],
        "lluvia_prevista": prevision["lluvia_prevista"] if prevision else None,
        "lluvia_mm_3h": registro["lluvia_mm"],
        "probabilidad_lluvia_pct_3h": registro["probabilidad_lluvia"],
        "siguiente_ventana_min": minutos_espera,
    })

    # --- Notificación a Telegram ---
    eventos_notificables = (
        orden_final != valvula_reportada
        or respuesta["motivo"] in (
            "HUMEDAD_CRITICA_DENTRO_VENTANA_RIEGO",
            "AHORRO_PREVISION_LLUVIA_AEMET",
            "COMANDO_MANUAL_CADUCADO",
        )
    )
    if eventos_notificables:
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

    # --- Actualización de estado global ---
    with _estado_lock:
        _ultima_telemetria = registro
        _ultimo_estado_valvula = orden_final

    logger.info(f"Respuesta: {orden_final} ({respuesta['motivo']}) | próxima ventana en {minutos_espera} min")

    return jsonify(respuesta), 200


@app.route("/api/v1/telemetria/export.csv", methods=["GET"])
def exportar_telemetria():
    """Exporta el histórico completo de telemetría en formato CSV."""
    return Response(
        exportar_telemetria_csv(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=telemetria_riego.csv"
        },
    )


# ==============================================================================
# ARRANQUE
# ==============================================================================
if __name__ == "__main__":
    # Bot de Telegram en hilo secundario
    iniciar_bot_polling(
        obtener_estado_manual,
        establecer_estado_manual,
        obtener_ultima_telemetria,
        contar_riegos_del_dia,
    )

    # Flask en el hilo principal
    # use_reloader=False: evita que el recargador de Flask duplique el polling de Telegram
    # debug se controla por variable de entorno (FLASK_DEBUG=true para desarrollo)
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, use_reloader=False)