from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
from dotenv import load_dotenv

from core.models import ClickAndFindEvent, events_to_dataframe


DEFAULT_DATABASE_PATH = "data/clickandfind.sqlite3"


def resolve_database_path(path: str | Path | None = None) -> str:
    load_dotenv()
    return str(path or os.getenv("DATABASE_PATH") or DEFAULT_DATABASE_PATH)


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    check_date TEXT NOT NULL,
    company TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    tractor_id TEXT,
    trailer_id TEXT,
    event_type TEXT NOT NULL,
    timestamp_start TEXT NOT NULL,
    timestamp_end TEXT NOT NULL,
    duration_minutes REAL NOT NULL,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    location_type TEXT,
    raw_text TEXT,
    source_section TEXT,
    severity TEXT NOT NULL,
    reasons TEXT,
    rule_ids TEXT,
    explanations TEXT,
    suggested_actions TEXT,
    risk_score INTEGER NOT NULL,
    control_status TEXT NOT NULL DEFAULT 'OK',
    codtrasp TEXT,
    tractor_plate TEXT,
    semitrailer_plate TEXT,
    terminal_id TEXT,
    raw_type TEXT,
    raw_op TEXT,
    rule_id TEXT,
    suggested_action TEXT,
    product TEXT,
    is_last_unload_for_product INTEGER NOT NULL DEFAULT 0,
    has_residual INTEGER NOT NULL DEFAULT 0,
    has_stop_on_residual INTEGER NOT NULL DEFAULT 0,
    has_stop_on_unload INTEGER NOT NULL DEFAULT 0,
    is_programming_like_load INTEGER NOT NULL DEFAULT 0,
    operation_duration_minutes REAL NOT NULL DEFAULT 0,
    location_confidence REAL NOT NULL DEFAULT 0,
    location_rule_source TEXT,
    location_notes TEXT
);
"""

MIGRATIONS = {
    "rule_ids": "ALTER TABLE events ADD COLUMN rule_ids TEXT",
    "explanations": "ALTER TABLE events ADD COLUMN explanations TEXT",
    "suggested_actions": "ALTER TABLE events ADD COLUMN suggested_actions TEXT",
    "control_status": "ALTER TABLE events ADD COLUMN control_status TEXT NOT NULL DEFAULT 'OK'",
    "codtrasp": "ALTER TABLE events ADD COLUMN codtrasp TEXT",
    "tractor_plate": "ALTER TABLE events ADD COLUMN tractor_plate TEXT",
    "semitrailer_plate": "ALTER TABLE events ADD COLUMN semitrailer_plate TEXT",
    "terminal_id": "ALTER TABLE events ADD COLUMN terminal_id TEXT",
    "raw_type": "ALTER TABLE events ADD COLUMN raw_type TEXT",
    "raw_op": "ALTER TABLE events ADD COLUMN raw_op TEXT",
    "rule_id": "ALTER TABLE events ADD COLUMN rule_id TEXT",
    "suggested_action": "ALTER TABLE events ADD COLUMN suggested_action TEXT",
    "product": "ALTER TABLE events ADD COLUMN product TEXT",
    "is_last_unload_for_product": "ALTER TABLE events ADD COLUMN is_last_unload_for_product INTEGER NOT NULL DEFAULT 0",
    "has_residual": "ALTER TABLE events ADD COLUMN has_residual INTEGER NOT NULL DEFAULT 0",
    "has_stop_on_residual": "ALTER TABLE events ADD COLUMN has_stop_on_residual INTEGER NOT NULL DEFAULT 0",
    "has_stop_on_unload": "ALTER TABLE events ADD COLUMN has_stop_on_unload INTEGER NOT NULL DEFAULT 0",
    "is_programming_like_load": "ALTER TABLE events ADD COLUMN is_programming_like_load INTEGER NOT NULL DEFAULT 0",
    "operation_duration_minutes": "ALTER TABLE events ADD COLUMN operation_duration_minutes REAL NOT NULL DEFAULT 0",
    "location_confidence": "ALTER TABLE events ADD COLUMN location_confidence REAL NOT NULL DEFAULT 0",
    "location_rule_source": "ALTER TABLE events ADD COLUMN location_rule_source TEXT",
    "location_notes": "ALTER TABLE events ADD COLUMN location_notes TEXT",
}


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(resolve_database_path(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute(SCHEMA)
        self._migrate(connection)
        return connection

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)")}
        for column, statement in MIGRATIONS.items():
            if column not in existing_columns:
                connection.execute(statement)

    def save_events(self, events: Iterable[ClickAndFindEvent]) -> None:
        df = events_to_dataframe(events)
        if df.empty:
            return
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO events (
                    event_id, check_date, company, vehicle_id, tractor_id, trailer_id,
                    event_type, timestamp_start, timestamp_end, duration_minutes,
                    latitude, longitude, location_name, location_type, raw_text,
                    source_section, severity, reasons, rule_ids, explanations,
                    suggested_actions, risk_score, control_status, codtrasp,
                    tractor_plate, semitrailer_plate, terminal_id, raw_type, raw_op,
                    rule_id, suggested_action, product, is_last_unload_for_product,
                    has_residual, has_stop_on_residual, has_stop_on_unload,
                    is_programming_like_load, operation_duration_minutes,
                    location_confidence, location_rule_source, location_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                df[
                    [
                        "event_id",
                        "check_date",
                        "company",
                        "vehicle_id",
                        "tractor_id",
                        "trailer_id",
                        "event_type",
                        "timestamp_start",
                        "timestamp_end",
                        "duration_minutes",
                        "latitude",
                        "longitude",
                        "location_name",
                        "location_type",
                        "raw_text",
                        "source_section",
                        "severity",
                        "reasons",
                        "rule_ids",
                        "explanations",
                        "suggested_actions",
                        "risk_score",
                        "control_status",
                        "codtrasp",
                        "tractor_plate",
                        "semitrailer_plate",
                        "terminal_id",
                        "raw_type",
                        "raw_op",
                        "rule_id",
                        "suggested_action",
                        "product",
                        "is_last_unload_for_product",
                        "has_residual",
                        "has_stop_on_residual",
                        "has_stop_on_unload",
                        "is_programming_like_load",
                        "operation_duration_minutes",
                        "location_confidence",
                        "location_rule_source",
                        "location_notes",
                    ]
                ].itertuples(index=False, name=None),
            )

    def load_events(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query("SELECT * FROM events ORDER BY timestamp_start DESC", connection)
