#ifndef GESTION_ENERGIA_H
#define GESTION_ENERGIA_H

#include "config.h"

// Contador en memoria RTC: sobrevive a deep sleep
RTC_DATA_ATTR static uint32_t contadorCiclos = 0;

enum EstadoBateria {
    BATERIA_CRITICA,
    BATERIA_BAJA,
    BATERIA_OK,
    BATERIA_LLENA
};

class GestionEnergia {
public:
    void iniciar() {
        // Atenuación del ADC: rango completo 0-3.3V (necesario para leer divisor de batería)
        // IMPORTANTE: solo pines del ADC1 funcionan con WiFi activo.
        // GPIO 35 pertenece a ADC1_CH7 → OK.
        analogSetPinAttenuation(PIN_BATERIA_ADC, ADC_11db);
        analogReadResolution(12);
    }

    uint32_t registrarCiclo() {
        contadorCiclos++;
        return contadorCiclos;
    }

    void resetearContador() {
        contadorCiclos = 0;
    }

    float leerVoltajeBateria() {
        #if MODO_SIMULACION
            return 3.30f; // LiFePO4 nominal en rango saludable
        #else
            // Media de 10 lecturas para reducir ruido del ADC
            const int N = 10;
            uint32_t suma = 0;
            for (int i = 0; i < N; i++) {
                suma += analogRead(PIN_BATERIA_ADC);
                delayMicroseconds(100);
            }
            float lecturaADC = suma / (float)N;
            // Divisor de tensión ×2 (dos resistencias iguales)
            // NOTA: lectura aproximada. Ver README para precision real con calibración.
            float voltaje = (lecturaADC / 4095.0f) * 3.3f * 2.0f;
            return voltaje;
        #endif
    }

    EstadoBateria evaluarBateria(float voltaje) {
        if (voltaje < 2.8f) return BATERIA_CRITICA;
        if (voltaje < 3.0f) return BATERIA_BAJA;
        if (voltaje < 3.4f) return BATERIA_OK;
        return BATERIA_LLENA;
    }

    const char* estadoBateriaStr(EstadoBateria e) {
        switch (e) {
            case BATERIA_CRITICA: return "CRITICA";
            case BATERIA_BAJA:    return "BAJA";
            case BATERIA_OK:      return "OK";
            case BATERIA_LLENA:   return "LLENA";
            default:              return "DESCONOCIDO";
        }
    }

    void entrarEnDeepSleep(uint32_t minutosSleep = TIEMPO_SLEEP_MIN) {
        // uint64_t previene desbordamiento en minutos > ~71
        uint64_t tiempoSleepUs = (uint64_t)minutosSleep * 60ULL * 1000000ULL;

        LOGF("\n------------------------------------------------\n");
        LOGF("[ENERGIA] Deep Sleep: %u minutos\n", minutosSleep);
        LOGF("[ENERGIA] Ciclo #%u completado.\n", contadorCiclos);
        LOGF("------------------------------------------------\n");

        #if DEBUG_MODE
            Serial.flush();
        #endif

        esp_sleep_enable_timer_wakeup(tiempoSleepUs);
        esp_deep_sleep_start();
    }
};

#endif