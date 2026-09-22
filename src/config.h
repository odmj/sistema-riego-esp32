#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==========================================
// 0. ENTORNO (inyectado por build_flags)
// ==========================================
// MODO_SIMULACION, MODO_PRUEBA_VALVULA y DEBUG_MODE
// se definen en platformio.ini según el entorno.
// Los defaults aquí son solo para compilación fuera de PlatformIO.

#ifndef MODO_SIMULACION
    #define MODO_SIMULACION 0
#endif

#ifndef MODO_PRUEBA_VALVULA
    #define MODO_PRUEBA_VALVULA 0
#endif

#ifndef DEBUG_MODE
    #define DEBUG_MODE 1
#endif

// Macros de log: desaparecen del binario cuando DEBUG_MODE=0
#if DEBUG_MODE
    #define LOG(x)      Serial.println(x)
    #define LOGF(...)   Serial.printf(__VA_ARGS__)
    #define LOGE(x)     Serial.println(x)   // Errores y alertas (siempre activos en dev)
#else
    #define LOG(x)      do {} while (0)
    #define LOGF(...)   do {} while (0)
    #define LOGE(x)     do {} while (0)     // En producción también silenciados
#endif

// ==========================================
// 1. ASIGNACIÓN DE PINES (ESP32 DevKit 30p)
// ==========================================
#define PIN_SENSOR_ADC    34   // ADC1_CH6 - sensor de humedad
#define PIN_SENSOR_VCC    25   // Alimentación conmutada del sensor
#define PIN_VALVULA_INA   26   // Puente H L9110S - canal A
#define PIN_VALVULA_INB   27   // Puente H L9110S - canal B
#define PIN_BATERIA_ADC   35   // ADC1_CH7 - divisor de tensión batería


// ==========================================
// 2. PARÁMETROS DE CICLO Y RIEGO
// ==========================================
#define TIEMPO_SLEEP_MIN           30   // Minutos entre ciclos de medición
#define DURACION_RIEGO_MIN         10   // Duración nominal de un riego
#define TIEMPO_MAX_RIEGO_MIN       15   // Seguridad: corte si backend no responde
#define TIEMPO_MIN_ENTRE_RIEGOS_H   6   // Seguridad: histéresis anti-rebote
#define PULSO_VALVULA_MS          100   // Pulso para válvula bistable (latching)

// ==========================================
// 3. CALIBRACIÓN DEL SENSOR CAPACITIVO
// ==========================================
#define CALIB_AIRE   3260   // ADC en seco   → 0%
#define CALIB_AGUA   1040   // ADC sumergido → 100%

// ==========================================
// 4. RED Y BACKEND
// ==========================================
// Las credenciales reales van en config_local.h (ignorado por Git).
// Si no existe, se usan placeholders.
#if __has_include("config_local.h")
    #include "config_local.h"
#else
    #warning "config_local.h no encontrado. Usando placeholders."
    #define WIFI_SSID       "CHANGE_ME"
    #define WIFI_PASSWORD   "CHANGE_ME"
    #define BACKEND_HOST    "127.0.0.1"
    #define BACKEND_PORT    5000
#endif

#define BACKEND_ENDPOINT  "/api/v1/telemetria"
#define WIFI_TIMEOUT_MS   8000

// ==========================================
// 5. LÓGICA LOCAL (FALLBACK SIN BACKEND)
// ==========================================
// Umbral crítico de humedad por debajo del cual se riega sí o sí
// aunque no haya comunicación con el backend.
#define UMBRAL_CRITICO_HUMEDAD   30   // % — por debajo, riego de emergencia

// Histéresis: si la humedad sube por encima de este valor tras un riego,
// no volver a regar hasta el siguiente ciclo normal.
#define UMBRAL_HISTERESIS        45   // % — por encima, no regar

// Duración del riego autónomo (independiente del backend)
// Puede coincidir con DURACION_RIEGO_MIN o ser un valor conservador.
#define DURACION_RIEGO_AUTONOMO_MIN  8

#define MAX_CICLOS_CRITICOS         3

#endif // CONFIG_H