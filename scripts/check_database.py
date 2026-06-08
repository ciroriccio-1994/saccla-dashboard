from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from storage.database import resolve_database_path


def main() -> None:
    load_dotenv()
    database_path = resolve_database_path()
    print(f"Database path used: {database_path}")

    path = Path(database_path)
    if not path.exists():
        raise SystemExit(f"Database file does not exist: {path}")

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        print(f"Available tables: {', '.join(tables) if tables else '(none)'}")

        if "events" not in tables:
            raise SystemExit("The events table is not available.")

        schema = list(connection.execute("PRAGMA table_info(events)"))
        columns = [row["name"] for row in schema]
        print("\nEvents schema:")
        for row in schema:
            print(
                f"- {row['name']} {row['type']} "
                f"not_null={bool(row['notnull'])} primary_key={bool(row['pk'])}"
            )

        total = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        print(f"\nTotal events: {total}")
        print_grouped(connection, "event_type", "Total events by event_type")
        print_grouped(connection, "source_section", "Total events by source_section")
        print_grouped(connection, "severity", "Total events by severity")
        if "codtrasp" in columns:
            print_grouped(connection, "codtrasp", "Total events by codtrasp")

        print("\nFirst 20 events:")
        dataframe = pd.read_sql_query(
            "SELECT * FROM events ORDER BY timestamp_start DESC LIMIT 20",
            connection,
        )
        if dataframe.empty:
            print("(none)")
        else:
            print(dataframe.to_string(index=False))


def print_grouped(connection: sqlite3.Connection, column: str, title: str) -> None:
    print(f"\n{title}:")
    rows = connection.execute(
        f"""
        SELECT COALESCE(NULLIF({column}, ''), '(empty)') AS value, COUNT(*) AS events
        FROM events
        GROUP BY value
        ORDER BY events DESC, value
        """
    )
    for row in rows:
        print(f"- {row['value']}: {row['events']}")


if __name__ == "__main__":
    main()
