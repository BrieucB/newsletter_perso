from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path, schema_path: Path | None = None) -> None:
    connection = connect(db_path)
    try:
        resolved_schema_path = schema_path or Path(__file__).with_name("schema.sql")
        connection.executescript(resolved_schema_path.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
