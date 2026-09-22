#ifndef RED_WIFI_H
#define RED_WIFI_H

#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>

class ModuloRed {
public:
    enum EstadoRed {
        RED_OK,
        RED_TIMEOUT,
        RED_SIN_CREDENCIALES,
        RED_OTRO
    };

    EstadoRed ultimoEstado = RED_OK;

    bool conectar() {
        #if MODO_SIMULACION
            LOG("[RED] Modo simulacion: conexion omitida\n");
            ultimoEstado = RED_OK;
            return true;
        #else
            LOGF("[RED] Conectando a: %s\n", WIFI_SSID);
            WiFi.mode(WIFI_STA);
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

            unsigned long inicio = millis();
            while (WiFi.status() != WL_CONNECTED) {
                delay(100);
                if (millis() - inicio > WIFI_TIMEOUT_MS) {
                    switch (WiFi.status()) {
                        case WL_NO_SSID_AVAIL:
                            ultimoEstado = RED_SIN_CREDENCIALES;
                            LOGE("[RED] SSID no disponible\n");
                            break;
                        case WL_CONNECT_FAILED:
                            ultimoEstado = RED_SIN_CREDENCIALES;
                            LOGE("[RED] Fallo de autenticacion\n");
                            break;
                        default:
                            ultimoEstado = RED_TIMEOUT;
                            LOGE("[RED] Timeout de conexion\n");
                    }
                    return false;
                }
            }

            ultimoEstado = RED_OK;
            LOGF("[RED] Conectado. IP: %s\n", WiFi.localIP().toString().c_str());
            return true;
        #endif
    }

    String enviarTelemetria(const String& payloadJson) {
        #if MODO_SIMULACION
            LOG("[RED] Respuesta HTTP simulada\n");
            return "{\"orden\":\"MANTENER\",\"motivo\":\"SIMULACION_OK\"}";
        #else
            if (WiFi.status() != WL_CONNECTED) {
                LOGE("[RED] Sin WiFi activo. Abortando envio.\n");
                return "";
            }

            HTTPClient http;
            String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT) + BACKEND_ENDPOINT;

            LOGF("[RED] POST a: %s\n", url.c_str());
            http.setTimeout(3000);
            http.begin(url);
            http.addHeader("Content-Type", "application/json");

            int httpCode = http.POST(payloadJson);
            String respuesta = "";

            if (httpCode > 0) {
                LOGF("[RED] Codigo HTTP: %d\n", httpCode);
                if (httpCode == HTTP_CODE_OK || httpCode == 201) {
                    respuesta = http.getString();
                } else {
                    LOGE("[RED] Codigo HTTP no esperado\n");
                }
            } else {
                LOGE("[RED] Error en peticion HTTP\n");
                LOGF("[RED] Detalle: %s\n", http.errorToString(httpCode).c_str());
            }

            http.end();
            return respuesta;
        #endif
    }

    void desconectar() {
        #if !MODO_SIMULACION
            WiFi.disconnect(true);
            WiFi.mode(WIFI_OFF);
            LOG("[RED] Antena apagada\n");
        #endif
    }
};

#endif