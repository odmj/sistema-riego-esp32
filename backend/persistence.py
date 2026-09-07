import csv
import io
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_PATH = os.path.join(DATA_DIR, "riego.sqlite3")


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def inicializar_bbdd():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recibido_en TEXT NOT NULL,
                dispositivo_id TEXT NOT NULL,
                ciclo INTEGER,
                humedad_suelo_pct REAL NOT NULL,
                bateria_v REAL NOT NULL,
                valvula_estado_reportado TEXT NOT NULL,
                orden_backend TEXT NOT NULL,
                motivo_decision TEXT NOT NULL,
                lluvia_prevista INTEGER,
                lluvia_mm_3h REAL,
                probabilidad_lluvia_pct_3h INTEGER,
                siguiente_ventana_min INTEGER
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_telemetria_recibido_en "
            "ON telemetria(recibido_en)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_telemetria_dispositivo_ciclo "
            "ON telemetria(dispositivo_id, ciclo)"
        )


def guardar_telemetria(telemetria):
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO telemetria (
                recibido_en,
                dispositivo_id,
                ciclo,
                humedad_suelo_pct,
                bateria_v,
                valvula_estado_reportado,
                orden_backend,
                motivo_decision,
                lluvia_prevista,
                lluvia_mm_3h,
                probabilidad_lluvia_pct_3h,
                siguiente_ventana_min
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telemetria["recibido_en"],
                telemetria["dispositivo_id"],
                telemetria["ciclo"],
                telemetria["humedad_suelo_pct"],
                telemetria["bateria_v"],
                telemetria["valvula_estado_reportado"],
                telemetria["orden_backend"],
                telemetria["motivo_decision"],
                telemetria["lluvia_prevista"],
                telemetria["lluvia_mm_3h"],
                telemetria["probabilidad_lluvia_pct_3h"],
                telemetria["siguiente_ventana_min"],
            ),
        )


def exportar_telemetria_csv():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM telemetria ORDER BY recibido_en, id"
        ).fetchall()

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows(tuple(row) for row in rows)
    return output.getvalue()


def ahora_utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
