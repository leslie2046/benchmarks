from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import psycopg

from backend.store import DEFAULT_DATABASE_URL, TABLE_COLUMNS, RunStore


def migrate_sqlite(source: Path, database_url: str) -> dict[str, int]:
    source = source.resolve(strict=True)
    store = RunStore(database_url, initialize=False)
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as legacy:
        legacy.execute("BEGIN")
        available = {row[0] for row in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"runs", "service_configs", "test_plans"}.issubset(available):
            raise ValueError("Source is not a PrismLab SQLite database")
        with store._session() as connection:
            store.create_tables(connection)
            connection.execute("LOCK TABLE " + ", ".join(TABLE_COLUMNS) + " IN EXCLUSIVE MODE")
            for table in TABLE_COLUMNS:
                if connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise ValueError("Target database must be empty; existing data will not be overwritten")
            counts = {}
            for table, columns in TABLE_COLUMNS.items():
                counts[table] = 0
                if table not in available:
                    continue
                names = ", ".join(columns)
                placeholders = ", ".join(["%s"] * len(columns))
                with connection.cursor() as cursor:
                    for row in legacy.execute(f"SELECT {names} FROM {table}"):
                        json.loads(row[-1])
                        cursor.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})", row)
                        counts[table] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a stopped PrismLab SQLite workspace into an empty PostgreSQL database")
    parser.add_argument("source", type=Path, help="Path to the existing runs.sqlite3 file (read-only)")
    arguments = parser.parse_args()
    try:
        counts = migrate_sqlite(arguments.source, os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    except (OSError, ValueError, sqlite3.Error, psycopg.Error) as error:
        parser.exit(1, f"Migration failed: {error}\n")
    print(json.dumps(counts, ensure_ascii=False))
    print("Migration committed. Keep the original secret.key (or BENCHMARK_SECRET_KEY) and reports directory.")


if __name__ == "__main__":
    main()
