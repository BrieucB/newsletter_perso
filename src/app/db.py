from __future__ import annotations

import sqlite3
from pathlib import Path

ITEM_COLUMN_MIGRATIONS = {
    "content_type": "TEXT",
    "fit_tag": "TEXT",
    "relevance_for_work": "REAL",
    "relevance_for_llm_learning": "REAL",
    "applicability_score": "REAL",
    "why_you_should_care_generated": "TEXT",
    "selection_reason_json": "TEXT",
}


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
        _apply_migrations(connection)
        connection.executescript(resolved_schema_path.read_text(encoding="utf-8"))
        _apply_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _apply_migrations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "items"):
        return
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(items)").fetchall()
    }
    for column_name, definition in ITEM_COLUMN_MIGRATIONS.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE items ADD COLUMN {column_name} {definition}")
