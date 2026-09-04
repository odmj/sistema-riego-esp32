#ifndef GESTION_ENERGIA_H
#define GESTION_ENERGIA_H

#include "config.h"

// Contador en memoria RTC para registrar cuántos despertares lleva la placa
RTC_DATA_ATTR static uint32_t contadorCiclos = 0;

class GestionEnergia {
public:
    void iniciar() {
        // Reservado para la configuración de atenuación ADC cuando se mida el voltaje de la LiFePO4
    }

    uint32_t registrarCiclo() {
        contadorCiclos++;
        return contadorCiclos;
    }

    float leerVoltajeBateria() {
        #if MODO_SIMULACION
            return 3.30f; // Voltaje nominal simulado (LiFePO4 en rango saludable)
        #else
            // HARDWARE REAL: Divisor de tensión
            int lecturaADC = analogRead(35);
            float voltaje = (lecturaADC / 4095.0f) * 3.3f * 2.0f;
            return voltaje;
        #endif
    }

    // Acepta minutos dinámicos como parámetro. Si no se especifican, usa TIEMPO_SLEEP_MIN por defecto
    void entrarEnDeepSleep(uint32_t minutosSleep = TIEMPO_SLEEP_MIN) {
        // Conversión a microsegundos (ULL previene desbordamientos de entero de 32 bits)
        uint64_t tiempoSleepUs = (uint64_t)minutosSleep * 60ULL * 1000000ULL;
        
        Serial.println("\n------------------------------------------------");
        Serial.printf("[ENERGÍA] Preparando Deep Sleep por %d minutos...\n", minutosSleep);
        Serial.printf("[ENERGÍA] Ciclo de trabajo #%d completado.\n", contadorCiclos);
        Serial.println("------------------------------------------------\n");
        Serial.flush(); // Vacía el búfer del puerto serie antes de cortar energía a la CPU

        // Configura el temporizador interno y apaga la CPU
        esp_sleep_enable_timer_wakeup(tiempoSleepUs);
        esp_deep_sleep_start();
    }
};

#endif