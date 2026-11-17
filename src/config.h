#ifndef CONFIG_H //include guard
#define CONFIG_H

#include <Arduino.h>

// ==========================================
// 0. ENTORNO (inyectado por build_flags)
// ==========================================
// MODO_SIMULACION y DEBUG_MODE
// se definen en platformio.ini según el entorno.
// Los defaults aquí son solo para compilación fuera de PlatformIO.

#ifndef MODO_SIMULACION
    #define MODO_SIMULACION 0
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
#define TIEMPO_SLEEP_NORMAL_MIN     60   // Frecuencia de muestreo normal (sin riego)
#define TIEMPO_SLEEP_ALERTA_MIN     30   // Despierta más a menudo si la humedad es crítica
#define TIEMPO_SLEEP_BATERIA_MIN    120  // Duerme más si la batería está baja

#define DURACION_RIEGO_NOMINAL_MIN  8   // Tiempo estándar que pide el backend
#define DURACION_RIEGO_MAX_MIN      10   // Cortafuegos absoluto (nunca regar más de esto)
#define DURACION_RIEGO_FALLBACK_MIN 8    // Tiempo de riego si no hay backend

#define HORAS_MIN_ENTRE_RIEGOS      2   // Candado: no regar dos veces en menos de 2h
#define PULSO_VALVULA_MS            1500 // Pulso para válvula bistable (1.5s, ajustable)

// ==========================================
// 3. LÓGICA LOCAL (FALLBACK SIN BACKEND)
// ==========================================
#define UMBRAL_CRITICO_HUMEDAD      20   // Por debajo, riego de emergencia
#define UMBRAL_HISTERESIS           30   // Por encima, se considera suelo sano
#define MAX_CICLOS_CRITICOS_CONSEC  3    // Si falla 3 veces, parar de intentar

// ==========================================
// 4. CALIBRACIÓN DEL SENSOR CAPACITIVO
// ==========================================
#define CALIB_AIRE   3260   // ADC en seco   → 0%
#define CALIB_AGUA   1040   // ADC sumergido → 100%

// ==========================================
// 5. RED Y BACKEND
// ==========================================
// Las credenciales reales van en config_local.h
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
#define WIFI_TIMEOUT_MS   10000

#endif // CONFIG_H