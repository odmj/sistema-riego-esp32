from flask import Flask, request, jsonify
from datetime import datetime

# Inicializamos la aplicación Flask
app = Flask(__name__)

# Variable global temporal para simular la orden manual desde el móvil
# Opciones: "AUTONOMO", "FORZAR_ABRIR", "FORZAR_CERRAR"
estado_manual_usuario = "AUTONOMO"

@app.route('/api/v1/telemetria', methods=['POST'])
def recibir_telemetria():
    global estado_manual_usuario
    
    # 1. Extraemos el JSON enviado por el ESP32
    datos = request.get_json()
    
    if not datos:
        return jsonify({"error": "Payload JSON invalido"}), 400

    # 2. Imprimimos los datos recibidos en la consola del servidor
    hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{hora_actual}] --- TELEMETRÍA RECIBIDA ---")
    print(f"  Dispositivo : {datos.get('dispositivo_id')}")
    print(f"  Ciclo       : #{datos.get('ciclo')}")
    print(f"  Batería     : {datos.get('bateria_v')} V")
    print(f"  Humedad     : {datos.get('humedad_suelo_pct')} %")
    print(f"  Válvula     : {datos.get('valvula_estado')}")

    # 3. Lógica de Decisión del Backend (Intersección Modo Manual vs. Modo Autónomo)
    respuesta = {}

    if estado_manual_usuario == "FORZAR_ABRIR":
        respuesta = {
            "orden": "ABRIR",
            "motivo": "ORDEN_MANUAL_DESDE_TELEGRAM"
        }
        # Una vez atendida la orden manual, volvemos al modo autónomo
        estado_manual_usuario = "AUTONOMO"

    elif estado_manual_usuario == "FORZAR_CERRAR":
        respuesta = {
            "orden": "CERRADA",
            "motivo": "CIERRE_MANUAL_DESDE_TELEGRAM"
        }
        estado_manual_usuario = "AUTONOMO"

    else:
        # Lógica Autónoma Local del Servidor (Preludio a la integración con AEMET)
        humedad = float(datos.get('humedad_suelo_pct', 0))
        
        if humedad < 25.0:
            respuesta = {
                "orden": "ABRIR",
                "motivo": "REGALA_HUMEDAD_BAJA_LOCAL"
            }
        else:
            respuesta = {
                "orden": "CERRADA",
                "motivo": "HUMEDAD_SUFICIENTE"
            }

    print(f"  Respuesta   : {respuesta['orden']} ({respuesta['motivo']})")
    print("-------------------------------------------\n")

    # 4. Devolvemos la respuesta JSON al ESP32 con código HTTP 200 (OK)
    return jsonify(respuesta), 200

if __name__ == '__main__':
    # Ejecutamos el servidor escuchando en todas las interfaces de red de tu PC (0.0.0.0) en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)