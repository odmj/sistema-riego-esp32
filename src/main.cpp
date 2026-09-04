#include <Arduino.h>
#include "config.h"
#include "sensor_humedad.h"
#include "valvula.h"
#include "gestion_energia.h"
#include "telemetria.h"
#include "red_wifi.h"

// Instanciamos los objetos
SensorHumedad sensor;
ControlValvula valvula;
GestionEnergia energia;
ModuloTelemetria telemetria;
ModuloRed red;

void setup() {
    Serial.begin(115200);
    delay(500); 

    uint32_t cicloActual = energia.registrarCiclo();

    Serial.println("==============================================");
    Serial.println("  SISTEMA DE RIEGO IoT - PROTOCOLO MONOCANAL  ");
    Serial.printf("  Ejecutando Ciclo #%d\n", cicloActual);
    Serial.println("==============================================");

    // 1. Inicialización de periféricos
    sensor.iniciar();
    valvula.iniciar();
    energia.iniciar();

    // 2. Lecturas de las instancias
    float vbat = energia.leerVoltajeBateria();
    float humedad = sensor.leerPorcentaje();
    EstadoValvula estadoActual = valvula.obtenerEstadoActual();

    // 3. Generación del Payload JSON
    String payload = telemetria.generarPayload(cicloActual, vbat, humedad, estadoActual);
    
    Serial.println("\n[TELEMETRÍA] Payload JSON listo para transmisión:");
    Serial.println(payload);

    // 4. Intento de conexión Wi-Fi y envío
    String respuestaServidor = "";
    if (red.conectar()) {
        respuestaServidor = red.enviarTelemetria(payload);
        red.desconectar(); // Apagamos la antena Wi-Fi inmediatamente tras el envío
    }

    // Variable para almacenar el tiempo de Deep Sleep sugerido
    uint32_t minutosSleep = 15; // Valor por defecto de seguridad (15 minutos)

    // 5. Evaluación de la decisión (Respuesta del Servidor o Fallback)
    if (respuestaServidor.length() > 0) {
        Serial.println("\n[SISTEMA] Procesando orden recibida del Backend...");
        OrdenServidor orden = telemetria.procesarRespuestaServidor(respuestaServidor);
        Serial.printf("[LOGICA] Motivo del servidor: %s\n", orden.motivo.c_str());

        if (orden.ejecutarCambio) {
            valvula.cambiarEstado(orden.nuevoEstado);
        }

        // Asignamos el tiempo devuelto por el backend
        minutosSleep = orden.minutosHastaProximaVentana;

    } else {
        // FALLBACK LOCAL: Si falla la red Wi-Fi, aplicamos una regla de emergencia básica
        Serial.println("\n[ALERTA] Sin comunicación con el servidor. Aplicando Lógica de Emergencia Local...");
        if (humedad < 20.0f) { // Solo riega si está extremadamente seco
            valvula.cambiarEstado(ABIERTA);
        } else {
            valvula.cambiarEstado(CERRADA);
        }
        minutosSleep = 15; // Reintento corto tras un fallo de red
    }

    // 6. Límites de seguridad para el Deep Sleep
    if (minutosSleep > 240) {
        minutosSleep = 240; // Máximo 4 horas para evitar desvíos del RTC
    }
    if (minutosSleep < 5) {
        minutosSleep = 5;   // Mínimo 5 minutos para evitar bucles de reinicio rápidos
    }

    Serial.printf("\n[ENERGÍA] Configurando Deep Sleep para los próximos %d minutos.\n", minutosSleep);

    // 7. Dormir el sistema con el tiempo dinámico calculado
    energia.entrarEnDeepSleep(minutosSleep);
}

void loop() {
    // Vacío (Deep Sleep activo)
}