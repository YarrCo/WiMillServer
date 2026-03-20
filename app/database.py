from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("WIMILL_DB_PATH", str(BASE_DIR / "wimill.db")))
STORAGE_DIR = Path(os.getenv("WIMILL_STORAGE_DIR", str(BASE_DIR / "storage")))
UPLOADS_DIR = STORAGE_DIR / "uploads"
DEVICES_DIR = STORAGE_DIR / "devices"
ONLINE_TIMEOUT_SECONDS = 30


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_storage() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def ensure_column(connection: sqlite3.Connection, table_name: str, definition: str) -> None:
    column_name = definition.split()[0]
    if column_name not in table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def init_db() -> None:
    init_storage()

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL UNIQUE,
                device_name TEXT,
                last_seen TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS allowed_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL UNIQUE,
                description TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL UNIQUE,
                firmware_version TEXT,
                last_seen TEXT,
                is_online INTEGER NOT NULL DEFAULT 0,
                connection_status TEXT NOT NULL DEFAULT 'offline',
                usb_status TEXT NOT NULL DEFAULT 'unknown',
                busy_status TEXT NOT NULL DEFAULT 'unknown',
                free_space INTEGER,
                total_space INTEGER,
                ip_address TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                modified_at TEXT,
                synced_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                direction TEXT NOT NULL,
                device_name TEXT,
                endpoint TEXT NOT NULL,
                event_type TEXT NOT NULL,
                request_summary TEXT,
                response_summary TEXT,
                status TEXT NOT NULL,
                details TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT,
                job_type TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                error_message TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'user',
                note TEXT
            )
            """
        )

        ensure_column(connection, "jobs", "device_id TEXT")
        ensure_column(connection, "jobs", "device_name TEXT")
        ensure_column(connection, "jobs", "updated_at TEXT")
        ensure_column(connection, "jobs", "error_message TEXT")
        ensure_column(connection, "jobs", "progress INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "jobs", "source TEXT NOT NULL DEFAULT 'user'")
        ensure_column(connection, "jobs", "note TEXT")

        connection.execute(
            """
            UPDATE jobs
            SET device_name = COALESCE(NULLIF(device_name, ''), device_id)
            WHERE (device_name IS NULL OR device_name = '')
              AND device_id IS NOT NULL
              AND device_id != ''
            """
        )
        connection.execute(
            """
            UPDATE jobs
            SET updated_at = COALESCE(updated_at, created_at, ?),
                progress = COALESCE(progress, 0),
                source = COALESCE(NULLIF(source, ''), 'user'),
                file_name = COALESCE(file_name, '')
            """,
            (utc_now(),),
        )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_device_status ON jobs (device_name, status, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log (timestamp DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_files_name ON device_files (device_name, file_name)"
        )
        connection.commit()
