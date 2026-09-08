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
            """
            CREATE TABLE IF NOT EXISTS riegos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iniciado_en TEXT NOT NULL,
                finalizado_en TEXT,
                duracion_programada_min INTEGER NOT NULL,
                humedad_inicio_pct REAL,
                humedad_fin_pct REAL,
                modo TEXT NOT NULL,
                motivo TEXT NOT NULL,
                lluvia_prevista INTEGER,
                dispositivo_id TEXT NOT NULL,
                ciclo_inicio INTEGER
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_riegos_iniciado_en "
            "ON riegos(iniciado_en)"
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


def registrar_inicio_riego(riego):
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO riegos (
                iniciado_en,
                duracion_programada_min,
                humedad_inicio_pct,
                modo,
                motivo,
                lluvia_prevista,
                dispositivo_id,
                ciclo_inicio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                riego["iniciado_en"],
                riego["duracion_programada_min"],
                riego["humedad_inicio_pct"],
                riego["modo"],
                riego["motivo"],
                riego["lluvia_prevista"],
                riego["dispositivo_id"],
                riego["ciclo_inicio"],
            ),
        )


def finalizar_ultimo_riego(humedad_fin_pct, finalizado_en):
    with _connect() as connection:
        connection.execute(
            """
            UPDATE riegos
            SET finalizado_en = ?, humedad_fin_pct = ?
            WHERE id = (
                SELECT id FROM riegos
                WHERE finalizado_en IS NULL
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (finalizado_en, humedad_fin_pct),
        )


def contar_riegos_del_dia(fecha=None):
    if fecha is None:
        fecha = datetime.now().date().isoformat()

    with _connect() as connection:
        fila = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM riegos
            WHERE date(iniciado_en, 'localtime') = ?
            """,
            (fecha,),
        ).fetchone()
    return fila["total"]


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
