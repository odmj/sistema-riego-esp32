#include <Arduino.h>
#include "config.h"
#include "sensor_humedad.h"
#include "valvula.h"
#include "gestion_energia.h"
#include "telemetria.h"
#include "red_wifi.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ==========================================
// INSTANCIAS DE MÓDULOS
// ==========================================
SensorHumedad    sensor;
ControlValvula   valvula;
GestionEnergia   energia;
ModuloTelemetria telemetria;
ModuloRed        red;

// ==========================================
// VARIABLES PERSISTENTES EN RTC
// Sobreviven al deep sleep, se pierden en reinicio total.
// El contador de ciclos vive en GestionEnergia (RTC_DATA_ATTR interno).
// ==========================================
RTC_DATA_ATTR uint8_t ciclosConHumedadCritica = 0;

// ==========================================
// SETUP (único punto de entrada en deep sleep)
// ==========================================
void setup() {
    // 1. Desactivar detector de brownout (al principio, antes de nada)
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    #if DEBUG_MODE
        Serial.begin(115200);
        delay(500);
    #endif

    // 2. Registrar ciclo en el módulo de energía
    uint32_t cicloActual = energia.registrarCiclo();

    LOGF("==============================================\n");
    LOGF("  SISTEMA DE RIEGO IoT - CICLO #%u\n", cicloActual);
    LOGF("==============================================\n");

    // 3. Inicialización de periféricos
    sensor.iniciar();
    valvula.iniciar();
    energia.iniciar();

    #if MODO_PRUEBA_VALVULA
        valvula.probarDirecciones();
        delay(2000);
        energia.entrarEnDeepSleep(5);
    #endif

    // 4. Lecturas
    float vbat    = energia.leerVoltajeBateria();
    float humedad = sensor.leerPorcentaje();
    EstadoValvula estadoActual = valvula.obtenerEstadoActual();

    EstadoBateria estadoBat = energia.evaluarBateria(vbat);
    LOGF("[ENERGIA] Bateria: %.2fV (%s)\n", vbat, energia.estadoBateriaStr(estadoBat));
    LOGF("[SENSOR] Humedad: %.1f%%\n", humedad);

    // 5. Generación de payload
    String payload = telemetria.generarPayload(cicloActual, vbat, humedad, estadoActual);
    LOGF("[TELEMETRIA] Payload: %s\n", payload.c_str());

    // 6. Envío al backend (una sola conexión)
    String respuestaServidor = "";
    if (red.conectar()) {
        respuestaServidor = red.enviarTelemetria(payload);
        red.desconectar();
    }

    // =====================================================
    // 7. DECISIÓN DE RIEGO
    // =====================================================
    uint32_t minutosSleep = TIEMPO_SLEEP_MIN;
    bool decisionTomadaPorBackend = false;

    // 7.1. Protección por batería crítica (prioridad máxima)
    if (estadoBat == BATERIA_CRITICA) {
        LOGE("[PROTECCION] Bateria critica. No se activa la valvula.\n");
        valvula.cambiarEstado(CERRADA);
        minutosSleep = TIEMPO_SLEEP_MIN * 4; // Dormir más para intentar recargar
    }
    // 7.2. Si hay respuesta del backend, obedecer (con límites de seguridad)
    else if (respuestaServidor.length() > 0) {
        LOG("[SISTEMA] Orden recibida del backend.\n");
        OrdenServidor orden = telemetria.procesarRespuestaServidor(respuestaServidor);
        LOGF("[LOGICA] Motivo: %s\n", orden.motivo.c_str());

        minutosSleep = orden.minutosHastaProximaVentana;

        if (orden.ejecutarCambio) {
            if (orden.nuevoEstado == ABIERTA) {
                uint32_t duracion = orden.duracionRiegoMin;
                if (duracion > TIEMPO_MAX_RIEGO_MIN) {
                    LOGE("[SEGURIDAD] Duracion excede maximo. Ajustando.\n");
                    duracion = TIEMPO_MAX_RIEGO_MIN;
                }
                minutosSleep = duracion;
            }
            valvula.cambiarEstado(orden.nuevoEstado);
        }

        decisionTomadaPorBackend = true;

        // Al recuperar comunicación, reseteamos el contador de críticos
        ciclosConHumedadCritica = 0;
    }

    // 7.3. Fallback: lógica local si el backend no responde
    if (!decisionTomadaPorBackend && estadoBat != BATERIA_CRITICA) {
        LOGE("[ALERTA] Sin backend. Modo autonomo local.\n");

        if (humedad < UMBRAL_CRITICO_HUMEDAD) {
            ciclosConHumedadCritica++;
            LOGF("[LOCAL] Humedad critica. Ciclos consecutivos: %u\n",
                 ciclosConHumedadCritica);

            if (ciclosConHumedadCritica > MAX_CICLOS_CRITICOS) {
                // El riego no está funcionando: no insistir
                LOGE("[ALERTA] Riego inefectivo tras varios ciclos. Revisar hardware.\n");
                valvula.cambiarEstado(CERRADA);
                minutosSleep = TIEMPO_SLEEP_MIN * 4; // Esperar más antes de reintentar
            } else {
                LOG("[LOCAL] Abriendo valvula por riego autonomo.\n");
                valvula.cambiarEstado(ABIERTA);
                minutosSleep = DURACION_RIEGO_AUTONOMO_MIN;
            }
        } else {
            LOG("[LOCAL] Humedad suficiente. No se riega.\n");
            valvula.cambiarEstado(CERRADA);
            minutosSleep = TIEMPO_SLEEP_MIN;
            ciclosConHumedadCritica = 0; // Reset al recuperar humedad
        }
    }

    // 8. Límites de seguridad para el deep sleep
    if (minutosSleep > 240) minutosSleep = 240; // Máx 4h (evita desvíos del RTC)
    if (minutosSleep < 5)   minutosSleep = 5;   // Mín 5 min (evita bucles)

    LOGF("[ENERGIA] Deep sleep: %u minutos\n", minutosSleep);
    energia.entrarEnDeepSleep(minutosSleep);
}

void loop() {
    // Vacío (deep sleep activo)
}