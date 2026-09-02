#ifndef RED_WIFI_H
#define RED_WIFI_H

#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>

class ModuloRed {
public:
    // Intenta conectar a la red Wi-Fi con un tiempo límite (timeout)
    bool conectar() {
        #if MODO_SIMULACION
            Serial.println("[RED] Modo Simulación: Omitiendo conexión Wi-Fi física.");
            return true;
        #else
            Serial.printf("[RED] Conectando a la red Wi-Fi: %s ...\n", WIFI_SSID);
            WiFi.mode(WIFI_STA);
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

            unsigned long inicioIntentos = millis();
            while (WiFi.status() != WL_CONNECTED) {
                delay(100);
                Serial.print(".");
                // Si sobrepasa el tiempo límite, aborta para cuidar la batería
                if (millis() - inicioIntentos > WIFI_TIMEOUT_MS) {
                    Serial.println("\n[RED] ERROR: Timeout al conectar a la red Wi-Fi.");
                    return false;
                }
            }

            Serial.println("\n[RED] ¡Conectado con éxito!");
            Serial.printf("[RED] Dirección IP asignada: %s\n", WiFi.localIP().toString().c_str());
            return true;
        #endif
    }

    // Envía el JSON por HTTP POST y devuelve la respuesta recibida del servidor
    String enviarTelemetria(const String& payloadJson) {
        #if MODO_SIMULACION
            Serial.println("[RED] Modo Simulación: Generando respuesta HTTP simulada.");
            return "{\"orden\":\"MANTENER\",\"motivo\":\"SIMULACION_OK\"}";
        #else
            if (WiFi.status() != WL_CONNECTED) {
                Serial.println("[RED] No hay conexión Wi-Fi activa para enviar datos.");
                return "";
            }

            HTTPClient http;
            String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT) + BACKEND_ENDPOINT;
            
            Serial.printf("[RED] Enviando POST a: %s\n", url.c_str());
            http.begin(url);
            http.addHeader("Content-Type", "application/json");

            int httpCode = http.POST(payloadJson);
            String respuesta = "";

            if (httpCode > 0) {
                Serial.printf("[RED] Respuesta HTTP del servidor: Código %d\n", httpCode);
                if (httpCode == HTTP_CODE_OK || httpCode == 201) {
                    respuesta = http.getString();
                }
            } else {
                Serial.printf("[RED] ERROR en petición HTTP: %s\n", http.errorToString(httpCode).c_str());
            }

            http.end(); // Libera los recursos de la pila TCP/IP
            return respuesta;
        #endif
    }

    // Desconecta la antena para garantizar cero consumo de red
    void desconectar() {
        #if !MODO_SIMULACION
            WiFi.disconnect(true);
            WiFi.mode(WIFI_OFF);
            Serial.println("[RED] Antena Wi-Fi apagada correctamente.");
        #endif
    }
};

#endif