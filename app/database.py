from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "wimill.db"
UPLOADS_DIR = BASE_DIR / "storage" / "uploads"
DEVICES_DIR = BASE_DIR / "storage" / "devices"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_storage() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)


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
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
