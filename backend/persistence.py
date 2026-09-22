"""
Capa de persistencia del sistema de riego.

Usa SQLite con dos tablas:
  - telemetria: series temporales (cada muestra del ESP32).
  - riegos:     eventos discretos con inicio/fin (trazabilidad y análisis).

Los timestamps se almacenan en UTC ISO 8601. La interpretación de "día local"
se hace explícitamente con zoneinfo (Europe/Madrid) para evitar acoplamiento
a la zona horaria del servidor.
"""

import csv
import io
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_PATH = os.path.join(DATA_DIR, "riego.sqlite3")

ZONA_LOCAL = ZoneInfo("Europe/Madrid")

# Conexión persistente por hilo (thread-safe sin reabrir en cada operación)
_local = threading.local()


def _connect():
    """
    Devuelve la conexión SQLite del hilo actual, creándola si es necesario.
    Usa WAL mode para permitir lecturas concurrentes sin bloquear escrituras.
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


def inicializar_bbdd():
    """Crea el esquema e índices si no existen."""
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_riegos_abiertos "
            "ON riegos(finalizado_en) WHERE finalizado_en IS NULL"
        )
    logger.info(f"Base de datos inicializada en {DATABASE_PATH}")


def guardar_telemetria(telemetria):
    """Inserta una muestra de telemetría."""
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
    """
    Registra el inicio de un riego.

    Cierra cualquier riego previo que hubiera quedado abierto (por ejemplo,
    tras un reinicio del backend), garantizando la invariante: como máximo
    un riego sin finalizar en todo momento.
    """
    with _connect() as connection:
        # Cerrar riegos huérfanos (abiertos sin finalizar)
        connection.execute(
            """
            UPDATE riegos
            SET finalizado_en = ?
            WHERE finalizado_en IS NULL
            """,
            (riego["iniciado_en"],),
        )
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
    logger.info(
        f"Riego iniciado | dispositivo={riego['dispositivo_id']} "
        f"ciclo=#{riego.get('ciclo_inicio')} motivo={riego['motivo']}"
    )


def finalizar_ultimo_riego(humedad_fin_pct, finalizado_en):
    """
    Marca como finalizado el riego abierto más reciente.
    Si no hay ninguno abierto, no hace nada.
    """
    with _connect() as connection:
        cursor = connection.execute(
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
        if cursor.rowcount > 0:
            logger.info(
                f"Riego finalizado | humedad_fin={humedad_fin_pct}%"
            )
        else:
            logger.warning(
                "Se solicitó finalizar riego pero no había ninguno abierto"
            )


def contar_riegos_del_dia(fecha=None):
    """
    Cuenta los riegos iniciados en un día, interpretado en la zona local
    (Europe/Madrid). El filtro en BD se hace en UTC para no depender de la
    zona horaria del servidor.
    """
    if fecha is None:
        fecha = datetime.now(ZONA_LOCAL).date()

    # Rango del día local convertido a UTC ISO
    inicio_local = datetime.combine(fecha, datetime.min.time(), tzinfo=ZONA_LOCAL)
    fin_local = inicio_local + timedelta(days=1)
    inicio_utc = inicio_local.astimezone(timezone.utc).isoformat(timespec="seconds")
    fin_utc = fin_local.astimezone(timezone.utc).isoformat(timespec="seconds")

    with _connect() as connection:
        fila = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM riegos
            WHERE iniciado_en >= ? AND iniciado_en < ?
            """,
            (inicio_utc, fin_utc),
        ).fetchone()
    return fila["total"]


def exportar_telemetria_csv():
    """Devuelve todo el histórico de telemetría como CSV (StringIO)."""
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
    """Timestamp actual en UTC, formato ISO 8601 con segundos."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")