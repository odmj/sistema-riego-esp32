#ifndef TELEMETRIA_H
#define TELEMETRIA_H

#include "config.h"
#include <ArduinoJson.h>
#include "valvula.h"

// Estructura C++ para almacenar de forma limpia la orden recibida del Backend/AEMET
struct OrdenServidor {
    bool ejecutarCambio;      // true si el servidor ordena cambiar el estado de la válvula
    EstadoValvula nuevoEstado; // ABIERTA o CERRADA
    String motivo;            // Ej: "AEMET_PREDICE_LLUVIA", "RIEGO_PROGRAMADO"
};

class ModuloTelemetria {
public:
    // Genera la cadena de texto JSON con las lecturas actuales del dispositivo
    String generarPayload(uint32_t ciclo, float bateriaV, float humedadPct, EstadoValvula estadoValvula) {
        // Reservamos un documento JSON estático de 256 bytes en memoria
        JsonDocument doc;

        // Poblamos las claves del JSON
        doc["dispositivo_id"] = "ESP32_RIEGO_01";
        doc["ciclo"] = ciclo;
        doc["bateria_v"] = serialized(String(bateriaV, 2));
        doc["humedad_suelo_pct"] = serialized(String(humedadPct, 1));
        doc["valvula_estado"] = (estadoValvula == ABIERTA) ? "ABIERTA" : "CERRADA";

        // Convertimos el objeto JSON a un String C++
        String payloadJson;
        serializeJson(doc, payloadJson);
        return payloadJson;
    }

    // Procesa el JSON de respuesta devuelto por el servidor en Python
    OrdenServidor procesarRespuestaServidor(const String& jsonRespuesta) {
        OrdenServidor ordenResultante;
        ordenResultante.ejecutarCambio = false;
        ordenResultante.motivo = "DESCONOCIDO";

        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, jsonRespuesta);

        if (error) {
            Serial.printf("[TELEMETRÍA] Error al parsear JSON del servidor: %s\n", error.c_str());
            return ordenResultante;
        }

        // Leemos la orden enviada por el backend ("ABRIR", "CERRAR", "MANTENER")
        const char* ordenStr = doc["orden"] | "MANTENER";
        const char* motivoStr = doc["motivo"] | "SIN_MOTIVO";
        
        ordenResultante.motivo = String(motivoStr);

        if (String(ordenStr) == "ABRIR") {
            ordenResultante.ejecutarCambio = true;
            ordenResultante.nuevoEstado = ABIERTA;
        } else if (String(ordenStr) == "CERRADA") {
            ordenResultante.ejecutarCambio = true;
            ordenResultante.nuevoEstado = CERRADA;
        }

        return ordenResultante;
    }

    // Función de simulación para probar el flujo sin servidor real por ahora
    String simularRespuestaBackend(float humedadActual) {
        // Simula la respuesta que construiría nuestro script de Python con AEMET
        JsonDocument doc;
        if (humedadActual < 30.0f) {
            doc["orden"] = "ABRIR";
            doc["motivo"] = "SUELO_SECO_SIN_LLUVIA_AEMET";
        } else {
            doc["orden"] = "CERRADA";
            doc["motivo"] = "HUMEDAD_OK_O_LLUVIA_PROXIMA";
        }
        
        String respuesta;
        serializeJson(doc, respuesta);
        return respuesta;
    }
};

#endif