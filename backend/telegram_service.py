"""
Bot de Telegram para telecontrol del sistema de riego.

Escucha comandos entrantes vía getUpdates (polling) y permite:
  - Forzar apertura/cierre de la válvula.
  - Volver a modo autónomo.
  - Consultar estado, última telemetría y riegos del día.

Solo responde al chat_id autorizado (TELEGRAM_CHAT_ID). Cualquier otro
origen se ignora y se registra como intento no autorizado.

Usa HTML como parse_mode para evitar roturas con Markdown.
"""

import html
import logging
import os
import threading
import time

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

if not TELEGRAM_TOKEN:
    logger.warning("TELEGRAM_TOKEN no configurado. El bot no funcionará.")
if not TELEGRAM_CHAT_ID:
    logger.warning("TELEGRAM_CHAT_ID no configurado. Nadie podrá controlar el bot.")


def _esc(valor):
    """Escapa caracteres HTML para evitar roturas e inyecciones."""
    return html.escape(str(valor)) if valor is not None else "N/D"


def enviar_alerta_telegram(mensaje_html):
    """
    Envía un mensaje HTML al chat autorizado.
    Devuelve True si el envío fue exitoso.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram no configurado. Mensaje omitido.")
        return False

    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            logger.error(
                f"Error enviando mensaje Telegram ({res.status_code}): {res.text}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Excepción enviando mensaje Telegram: {e}")
        return False


def _formatear_help():
    return (
        "🤖 <b>Bot de Control de Riego IoT</b>\n\n"
        "<b>Comandos disponibles:</b>\n"
        "• <code>/regar</code> — Forzar apertura en la próxima ventana\n"
        "• <code>/cerrar</code> — Forzar cierre inmediato\n"
        "• <code>/autonomo</code> — Volver al modo automático (AEMET + humedad)\n"
        "• <code>/estado</code> — Consultar el modo actual\n"
        "• <code>/telemetria</code> — Última lectura recibida\n"
        "• <code>/riegos_hoy</code> — Riegos iniciados hoy"
    )


def _formatear_telemetria(t):
    return (
        "📡 <b>Última telemetría recibida</b>\n"
        f"• <b>Hora:</b> <code>{_esc(t.get('hora'))}</code>\n"
        f"• <b>Dispositivo:</b> <code>{_esc(t.get('dispositivo'))}</code>\n"
        f"• <b>Ciclo:</b> <code>{_esc(t.get('ciclo'))}</code>\n"
        f"• <b>Humedad:</b> {_esc(t.get('humedad'))}%\n"
        f"• <b>Batería:</b> {_esc(t.get('bateria'))} V\n"
        f"• <b>Válvula reportada:</b> <code>{_esc(t.get('valvula'))}</code>\n"
        f"• <b>Orden backend:</b> <code>{_esc(t.get('orden'))}</code>\n"
        f"• <b>Motivo:</b> <code>{_esc(t.get('motivo'))}</code>\n"
        f"• <b>Lluvia próx. 3h:</b> "
        f"{_esc(t['lluvia_mm']) if t.get('lluvia_mm') is not None else 'No consultada'} mm\n"
        f"• <b>Probabilidad próx. 3h:</b> "
        f"{_esc(t['probabilidad_lluvia']) if t.get('probabilidad_lluvia') is not None else 'No consultada'}%\n"
        f"• <b>Siguiente chequeo:</b> {_esc(t.get('siguiente_ventana_min'))} min"
    )


def _procesar_comando(
    cmd,
    get_estado_func,
    set_estado_func,
    get_telemetria_func,
    contar_riegos_func,
):
    """Despacha el comando recibido y envía la respuesta adecuada."""

    if cmd in ("/start", "/help"):
        enviar_alerta_telegram(_formatear_help())

    elif cmd == "/regar":
        set_estado_func("FORZAR_ABRIR")
        enviar_alerta_telegram(
            "✅ <b>Orden registrada:</b> se forzará la <b>APERTURA</b> "
            "de la válvula en la próxima ventana de riego."
        )

    elif cmd == "/cerrar":
        set_estado_func("FORZAR_CERRAR")
        enviar_alerta_telegram(
            "⛔ <b>Orden registrada:</b> se forzará el <b>CIERRE</b> "
            "de la válvula en el próximo ciclo."
        )

    elif cmd == "/autonomo":
        set_estado_func("AUTONOMO")
        enviar_alerta_telegram(
            "🔄 <b>Modo Autónomo reanudado:</b> el sistema decidirá basándose "
            "en humedad del suelo y previsión de AEMET."
        )

    elif cmd == "/estado":
        modo = get_estado_func() if get_estado_func else "DESCONOCIDO"
        enviar_alerta_telegram(f"📊 <b>Estado actual:</b> <code>{_esc(modo)}</code>")

    elif cmd in ("/telemetria", "/ultima"):
        telemetria = get_telemetria_func() if get_telemetria_func else None
        if not telemetria:
            enviar_alerta_telegram("ℹ️ Todavía no se ha recibido telemetría.")
        else:
            enviar_alerta_telegram(_formatear_telemetria(telemetria))

    elif cmd == "/riegos_hoy":
        total = contar_riegos_func() if contar_riegos_func else 0
        enviar_alerta_telegram(
            f"💧 <b>Riegos iniciados hoy:</b> <code>{total}</code>"
        )

    else:
        enviar_alerta_telegram(
            f"❓ Comando no reconocido: <code>{_esc(cmd)}</code>\n\n"
            + _formatear_help()
        )


def _bucle_polling(
    get_estado_func,
    set_estado_func,
    get_telemetria_func,
    contar_riegos_func,
    stop_event=None,
):
    """
    Bucle de polling de Telegram. Diseñado para correr en un hilo daemon.
    Aplica backoff exponencial ante errores de red.
    """
    last_update_id = 0
    backoff = 1
    logger.info("Bot de Telegram iniciado (polling activo)")

    while not (stop_event and stop_event.is_set()):
        try:
            url = f"{BASE_URL}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 10}
            res = requests.get(url, params=params, timeout=12)

            if res.status_code != 200:
                logger.error(
                    f"Telegram getUpdates error ({res.status_code}): {res.text}"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            backoff = 1  # Reset tras éxito

            data = res.json()
            for update in data.get("result", []):
                last_update_id = update["update_id"]
                message = update.get("message", {})
                text = (message.get("text") or "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                # Validación de origen autorizado
                if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                    logger.warning(
                        f"Intento de acceso no autorizado desde chat_id={chat_id}"
                    )
                    continue

                if not text:
                    continue

                cmd = text.split()[0].lower()
                logger.info(f"Comando recibido: {cmd}")
                _procesar_comando(
                    cmd,
                    get_estado_func,
                    set_estado_func,
                    get_telemetria_func,
                    contar_riegos_func,
                )

        except Exception as e:
            logger.error(f"Error en polling de Telegram: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    logger.info("Bot de Telegram detenido")


def iniciar_bot_polling(
    get_estado_func,
    set_estado_func,
    get_telemetria_func=None,
    contar_riegos_func=None,
):
    """Arranca el bot de Telegram en un hilo daemon."""
    if not TELEGRAM_TOKEN:
        logger.warning("Token de Telegram inválido. Polling deshabilitado.")
        return None

    stop_event = threading.Event()
    hilo = threading.Thread(
        target=_bucle_polling,
        args=(
            get_estado_func,
            set_estado_func,
            get_telemetria_func,
            contar_riegos_func,
            stop_event,
        ),
        daemon=True,
        name="telegram-polling",
    )
    hilo.start()
    return stop_event