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
    digitalWrite(PIN_SENSOR_VCC, LOW);
    analogSetPinAttenuation(PIN_SENSOR_ADC, ADC_11db);
    analogReadResolution(12);
    }

    // Lee la humedad actual y devuelve el valor mapeado en Porcentaje (0% - 100%)
    float leerPorcentaje() {
    #if MODO_SIMULACION
        // Variación simulada realista
        if (humedad_simulada < 60) humedad_simulada += 15;
        LOGF("[SIM] Humedad simulada: %d%%\n", humedad_simulada);
        return (float)humedad_simulada;
    #else
        digitalWrite(PIN_SENSOR_VCC, HIGH);
        delay(30);

        // Media de 10 lecturas para reducir ruido
        const int N = 10;
        uint32_t suma = 0;
        for (int i = 0; i < N; i++) {
            suma += analogRead(PIN_SENSOR_ADC);
            delayMicroseconds(100);
        }
        int lecturaADC = suma / N;

        digitalWrite(PIN_SENSOR_VCC, LOW);

        // Sensor capacitivo: mayor ADC = menos humedad
        float porcentaje = (float)(lecturaADC - CALIB_AIRE) * 100.0f
                         / (float)(CALIB_AGUA - CALIB_AIRE);
        return constrain(porcentaje, 0.0f, 100.0f);
    #endif
    }

    // Método auxiliar para utilizar otros valores de humedad en modo simulación
    void setHumedadSimulada(int nuevoValor) {
        humedad_simulada = nuevoValor;
    }
};

#endif