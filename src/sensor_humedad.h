#ifndef SENSOR_HUMEDAD_H
#define SENSOR_HUMEDAD_H

#include "config.h"

// Variable en Memoria RTC para simular variaciones de humedad entre ciclos de Deep Sleep
RTC_DATA_ATTR static int humedad_simulada = 22; // Inicia en 22% (Seco para forzar riego al arrancar)

class SensorHumedad {
public:
    // Configura el pin que alimentará al sensor de forma puntual
    void iniciar() {
        pinMode(PIN_SENSOR_VCC, OUTPUT);
        digitalWrite(PIN_SENSOR_VCC, LOW); // Apagado por defecto
    }

    // Lee la humedad actual y devuelve el valor mapeado en Porcentaje (0% - 100%)
    float leerPorcentaje() {
        #if MODO_SIMULACION
            Serial.println("[SENSOR] Modo Simulación activo.");
            Serial.printf("[SENSOR] Humedad simulación leída: %d%%\n", humedad_simulada);
            return (float)humedad_simulada;
        #else
            // --- HARDWARE REAL ---
            // 1. Encendemos el sensor aplicando 3.3V desde el pin GPIO
            digitalWrite(PIN_SENSOR_VCC, HIGH);
            delay(30); // Espera de 30ms para estabilizar la tensión y el sensor

            // 2. Lectura del valor analógico ADC (0 a 4095 en ESP32)
            int lecturaADC = analogRead(PIN_SENSOR_ADC);

            // 3. Apagamos el sensor inmediatamente (Ahorro de batería y evita corrosión)
            digitalWrite(PIN_SENSOR_VCC, LOW);

            // 4. Mapeo del valor del ADC a porcentaje
            // Recordar: CALIB_AIRE (3200) es 0% y CALIB_AGUA (1500) es 100%
            float porcentaje = map(lecturaADC, CALIB_AIRE, CALIB_AGUA, 0, 100);

            //  Límite de rango entre 0.0 y 100.0 por seguridad
            return constrain(porcentaje, 0.0f, 100.0f);
        #endif
    }

    // Método auxiliar para utilizar otros valores de humedad en modo simulación
    void setHumedadSimulada(int nuevoValor) {
        humedad_simulada = nuevoValor;
    }
};

#endif