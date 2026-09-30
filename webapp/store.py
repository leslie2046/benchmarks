from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp.model_configs import configured_models


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class RunStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS service_configs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS test_plans (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            rows = connection.execute(
                "SELECT id, payload FROM runs WHERE status IN ('queued', 'running')"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload["status"] = "failed"
                payload["error"] = "Server restarted before the run finished"
                payload["updated_at"] = utc_now()
                connection.execute(
                    "UPDATE runs SET status = ?, updated_at = ?, payload = ? WHERE id = ?",
                    ("failed", payload["updated_at"], json.dumps(payload), row["id"]),
                )
            completed_rows = connection.execute(
                "SELECT id, payload FROM runs WHERE status = 'completed'"
            ).fetchall()
            for row in completed_rows:
                payload = json.loads(row["payload"])
                changed = False
                for scenario in payload.get("scenarios", []):
                    result = scenario.get("result") or {}
                    if scenario.get("status") == "completed" and result.get("success_count", 0) == 0:
                        scenario["status"] = "failed"
                        scenario["error"] = "No requests succeeded; check the Endpoint, credentials, model and server logs"
                        changed = True
                if changed and not any(item.get("status") == "completed" for item in payload.get("scenarios", [])):
                    payload["status"] = "failed"
                    payload["error"] = "All benchmark scenarios failed"
                if changed:
                    payload["updated_at"] = utc_now()
                    connection.execute(
                        "UPDATE runs SET status = ?, updated_at = ?, payload = ? WHERE id = ?",
                        (payload["status"], payload["updated_at"], json.dumps(payload), row["id"]),
                    )

    def create(self, run: dict[str, Any]) -> None:
        with self._session() as connection:
            connection.execute(
                "INSERT INTO runs (id, created_at, updated_at, status, payload) VALUES (?, ?, ?, ?, ?)",
                (
                    run["id"],
                    run["created_at"],
                    run["updated_at"],
                    run["status"],
                    json.dumps(run, ensure_ascii=False),
                ),
            )

    def save(self, run: dict[str, Any]) -> None:
        run["updated_at"] = utc_now()
        with self._session() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, updated_at = ?, payload = ? WHERE id = ?",
                (
                    run["status"],
                    run["updated_at"],
                    json.dumps(run, ensure_ascii=False),
                    run["id"],
                ),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._session() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            return cursor.rowcount > 0

    def put_service_config(self, config: dict[str, Any]) -> None:
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO service_configs (id, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload
                """,
                (config["id"], config["created_at"], config["updated_at"], json.dumps(config, ensure_ascii=False)),
            )

    def get_service_config(self, config_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT payload FROM service_configs WHERE id = ?", (config_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_service_configs(self, benchmark: str | None = None) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM service_configs ORDER BY created_at"
            ).fetchall()
        configs = [json.loads(row["payload"]) for row in rows]
        return [item for item in configs if not benchmark or any(model["benchmark"] == benchmark for model in configured_models(item))]

    def delete_service_config(self, config_id: str) -> bool:
        with self._session() as connection:
            cursor = connection.execute("DELETE FROM service_configs WHERE id = ?", (config_id,))
            return cursor.rowcount > 0

    def has_active_run_for_config(self, config_id: str) -> bool:
        with self._session() as connection:
            rows = connection.execute("SELECT payload FROM runs WHERE status IN ('queued', 'running')").fetchall()
        return any(
            scenario.get("service_config_id") == config_id
            for row in rows for scenario in json.loads(row["payload"]).get("scenarios", [])
        )

    def put_plan(self, plan: dict[str, Any]) -> None:
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO test_plans (id, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload
                """,
                (plan["id"], plan["created_at"], plan["updated_at"], json.dumps(plan, ensure_ascii=False)),
            )

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT payload FROM test_plans WHERE id = ?", (plan_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_plans(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM test_plans ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
