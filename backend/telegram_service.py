import os
import time
import requests
import threading
from dotenv import load_dotenv

# Encuentra la ruta absoluta del archivo .env localizado en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')

# Carga las variables desde la raíz
load_dotenv(dotenv_path=ENV_PATH)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def enviar_alerta_telegram(mensaje):
    """Envia un mensaje Markdown directamente al chat configurado."""
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token no configurado. Mensaje omitido.")
        return False

    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            print(f"[TELEGRAM] Error enviando mensaje ({res.status_code}): {res.text}")
            return False
        return True
    except Exception as e:
        print(f"[TELEGRAM] Error al enviar mensaje: {e}")
        return False


def _bucle_polling(
    get_estado_func,
    set_estado_func,
    get_telemetria_func,
    contar_riegos_func,
):
    """Bucle en segundo plano que escucha comandos entrantes mediante getUpdates."""
    last_update_id = 0
    print("[TELEGRAM] Oyente de comandos iniciado (Polling activo)...")

    while True:
        try:
            url = f"{BASE_URL}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 10}
            res = requests.get(url, params=params, timeout=12)

            if res.status_code == 200:
                data = res.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    message = update.get("message", {})
                    text = message.get("text", "").strip()
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    # Seguridad: Validar que el comando venga del chat autorizado
                    if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                        print(f"[TELEGRAM] Intento de acceso no autorizado desde Chat ID: {chat_id}")
                        continue

                    if not text:
                        continue

                    # Procesamiento de Comandos
                    cmd = text.split()[0].lower()

                    if cmd in ["/start", "/help"]:
                        msj = (
                            "🤖 *Bot de Control de Riego IoT*\n\n"
                            "Comandos disponibles:\n"
                            "• `/regar` - Forzar apertura en el próximo ciclo\n"
                            "• `/cerrar` - Forzar cierre en el próximo ciclo\n"
                            "• `/autonomo` - Volver al modo automático (AEMET + Humedad)\n"
                            "• `/estado` - Consultar el modo actual del sistema\n"
                            "• `/telemetria` - Consultar la última lectura recibida\n"
                            "• `/ultima` - Alias de `/telemetria`\n"
                            "• `/riegos_hoy` - Consultar los riegos iniciados hoy"
                        )
                        enviar_alerta_telegram(msj)

                    elif cmd == "/regar":
                        set_estado_func("FORZAR_ABRIR")
                        enviar_alerta_telegram("✅ *Orden registrada:* Se forzará la *APERTURA* de la válvula en la próxima conexión del ESP32.")

                    elif cmd == "/cerrar":
                        set_estado_func("FORZAR_CERRAR")
                        enviar_alerta_telegram("⛔ *Orden registrada:* Se forzará el *CIERRE* de la válvula en la próxima conexión del ESP32.")

                    elif cmd == "/autonomo":
                        set_estado_func("AUTONOMO")
                        enviar_alerta_telegram("🔄 *Modo Autónomo reanudado:* El sistema tomará decisiones basándose en humedad del suelo y AEMET.")

                    elif cmd == "/estado":
                        modo = get_estado_func()
                        enviar_alerta_telegram(f"📊 *Estado Actual del Servidor:* `{modo}`")

                    elif cmd in ["/telemetria", "/ultima"]:
                        telemetria = get_telemetria_func() if get_telemetria_func else None
                        if not telemetria:
                            enviar_alerta_telegram("ℹ️ Todavía no se ha recibido ninguna telemetría.")
                        else:
                            mensaje = (
                                "📡 *Última telemetría recibida*\n"
                                f"• *Hora:* `{telemetria['hora']}`\n"
                                f"• *Dispositivo:* `{telemetria['dispositivo']}`\n"
                                f"• *Ciclo:* `{telemetria['ciclo']}`\n"
                                f"• *Humedad:* {telemetria['humedad']}%\n"
                                f"• *Batería:* {telemetria['bateria']} V\n"
                                f"• *Válvula reportada:* `{telemetria['valvula']}`\n"
                                f"• *Orden backend:* `{telemetria['orden']}`\n"
                                f"• *Motivo:* `{telemetria['motivo']}`\n"
                                f"• *Lluvia próxima 3h:* {telemetria['lluvia_mm'] if telemetria['lluvia_mm'] is not None else 'No consultada'} mm\n"
                                f"• *Probabilidad próxima 3h:* {telemetria['probabilidad_lluvia'] if telemetria['probabilidad_lluvia'] is not None else 'No consultada'}%\n"
                                f"• *Siguiente chequeo:* {telemetria['siguiente_ventana_min']} min"
                            )
                            enviar_alerta_telegram(mensaje)

                    elif cmd == "/riegos_hoy":
                        total = contar_riegos_func() if contar_riegos_func else 0
                        enviar_alerta_telegram(
                            f"💧 *Riegos iniciados hoy:* `{total}`"
                        )

            else:
                print(f"[TELEGRAM] Error en getUpdates ({res.status_code}): {res.text}")

        except Exception as e:
            print(f"[TELEGRAM] Error en polling: {e}")
            time.sleep(5)

        time.sleep(1)


def iniciar_bot_polling(
    get_estado_func,
    set_estado_func,
    get_telemetria_func=None,
    contar_riegos_func=None,
):
    """Inicia el bot en un hilo secundario independiente de Flask."""
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token invalido. Polling deshabilitado.")
        return

    hilo = threading.Thread(
        target=_bucle_polling,
        args=(get_estado_func, set_estado_func, get_telemetria_func, contar_riegos_func),
        daemon=True
    )
    hilo.start()