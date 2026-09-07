#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==========================================
// 1. MODO DE EJECUCIÓN
// ==========================================
#define MODO_SIMULACION false

// ==========================================
// 2. ASIGNACIÓN DE PINES (ESP32 DevKit 30p)
// ==========================================
#define PIN_SENSOR_ADC   34   // Pin analógico donde lee la humedad (Solo entrada)
#define PIN_SENSOR_VCC   25   // Pin GPIO para alimentar el sensor (Evita corrosión)
#define PIN_VALVULA_INA  26   // Control A del Puente H (L9110S)
#define PIN_VALVULA_INB  27   // Control B del Puente H (L9110S)

// ==========================================
// 3. PARÁMETROS ENERGÉTICOS Y DE TIEMPO
// ==========================================
#define TIEMPO_SLEEP_MIN    30   // Tiempo a dormir entre mediciones (Minutos)
#define PULSO_VALVULA_MS    100  // Ancho del pulso de 9V para la válvula (Milisegundos)

// ==========================================
// 4. CALIBRACIÓN DEL SENSOR CAPACITIVO
// ==========================================
#define CALIB_AIRE          3260 // Valor ADC en seco (0% humedad)
#define CALIB_AGUA          1040 // Valor ADC sumergido (100% humedad)

// --- CONFIGURACIÓN DE RED Y BACKEND ---
#define WIFI_SSID       "AIREON654846"
#define WIFI_PASSWORD   "d74hdf8dy3h"

// Parámetros del servidor Backend (Python Flask) que recibe la telemetría y decide si abrir o cerrar la válvula
#define BACKEND_HOST    "192.168.1.154" 
#define BACKEND_PORT    5000
#define BACKEND_ENDPOINT "/api/v1/telemetria"

// Tiempo máximo de espera para conexión Wi-Fi en milisegundos (Ahorro de batería)
#define WIFI_TIMEOUT_MS 8000



#endif