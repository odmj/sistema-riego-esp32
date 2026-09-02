#ifndef VALVULA_H
#define VALVULA_H

#include "config.h"

enum EstadoValvula {
    CERRADA = 0,
    ABIERTA = 1
};

// --- VARIABLE EN MEMORIA RTC ---
// 'RTC_DATA_ATTR' guarda esta variable en la memoria que NO se borra durante el Deep Sleep.
RTC_DATA_ATTR static EstadoValvula estadoRTC = CERRADA;

class ControlValvula {
public:
    // Método para inicializar los pines del puente H (L9110S)
    void iniciar() {
        pinMode(PIN_VALVULA_INA, OUTPUT);
        pinMode(PIN_VALVULA_INB, OUTPUT);
        digitalWrite(PIN_VALVULA_INA, LOW);
        digitalWrite(PIN_VALVULA_INB, LOW);
    }

    // Devuelve el estado guardado en la memoria RTC
    EstadoValvula obtenerEstadoActual() {
        return estadoRTC;
    }

    // Aplica el cambio de estado (abrir/cerrar) solo si es necesario
    void cambiarEstado(EstadoValvula nuevoEstado) {
        // REGLA DE EFICIENCIA: Si el estado deseado es igual al actual, NO gastamos batería
        if (estadoRTC == nuevoEstado) {
            Serial.println("[VALVULA] El estado no ha cambiado. Se omite el pulso eléctrico.");
            return;
        }

        #if MODO_SIMULACION
            // Lógica en modo simulación (sin hardware físico)
            if (nuevoEstado == ABIERTA) {
                Serial.println("[SIMULACIÓN] Válvula -> ABIERTA (Pulso +9V simulado enviado)");
            } else {
                Serial.println("[SIMULACIÓN] Válvula -> CERRADA (Pulso -9V simulado enviado)");
            }
        #else
            // Lógica con HARDWARE REAL (Inversión de polaridad mediante Puente H L9110S)
            if (nuevoEstado == ABIERTA) {
                digitalWrite(PIN_VALVULA_INA, HIGH);
                digitalWrite(PIN_VALVULA_INB, LOW);
                delay(PULSO_VALVULA_MS);
            } else {
                digitalWrite(PIN_VALVULA_INA, LOW);
                digitalWrite(PIN_VALVULA_INB, HIGH);
                delay(PULSO_VALVULA_MS);
            }
            // Desactivar ambos pines para dejar el L9110S sin consumo en reposo
            digitalWrite(PIN_VALVULA_INA, LOW);
            digitalWrite(PIN_VALVULA_INB, LOW);
        #endif

        // Actualizamos la variable guardada en la Memoria RTC
        estadoRTC = nuevoEstado;
    }
};

#endif