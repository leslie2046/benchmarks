from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.model_configs import configured_models


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DEFAULT_DATABASE_URL = "postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab"
TABLE_COLUMNS = {
    "system_settings": ("id", "payload"),
    "run_ai_reports": ("run_id", "payload"),
    "runs": ("id", "created_at", "updated_at", "status", "payload"),
    "service_configs": ("id", "created_at", "updated_at", "payload"),
    "test_plans": ("id", "created_at", "updated_at", "payload"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class RunStore:
    def __init__(self, database_url: str, *, initialize: bool = True):
        self.database_url = database_url
        if initialize:
            self.initialize()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=10)

    @contextmanager
    def _session(self):
        with self._connect() as connection:
            yield connection

    @staticmethod
    def create_tables(connection: psycopg.Connection) -> None:
        for table, columns in TABLE_COLUMNS.items():
            definitions = [
                f"{column} {'INTEGER' if table == 'system_settings' and column == 'id' else 'TEXT'}"
                f"{' PRIMARY KEY' if index == 0 else ' NOT NULL'}"
                for index, column in enumerate(columns)
            ]
            connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(definitions)})")

    def initialize(self) -> None:
        with self._session() as connection:
            self.create_tables(connection)
            for row in connection.execute("SELECT run_id, payload FROM run_ai_reports").fetchall():
                report = json.loads(row["payload"])
                if report.get("status") == "generating":
                    report.update(status="failed", error="分析因服务重启中断，请重新分析。")
                    connection.execute("UPDATE run_ai_reports SET payload=%s WHERE run_id=%s", (json.dumps(report), row["run_id"]))
            rows = connection.execute(
                "SELECT id, payload FROM runs WHERE status IN ('queued', 'running')"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload["status"] = "failed"
                payload["error"] = "Server restarted before the run finished"
                payload["updated_at"] = utc_now()
                connection.execute(
                    "UPDATE runs SET status = %s, updated_at = %s, payload = %s WHERE id = %s",
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
                        "UPDATE runs SET status = %s, updated_at = %s, payload = %s WHERE id = %s",
                        (payload["status"], payload["updated_at"], json.dumps(payload), row["id"]),
                    )

    def create(self, run: dict[str, Any]) -> None:
        with self._session() as connection:
            connection.execute(
                "INSERT INTO runs (id, created_at, updated_at, status, payload) VALUES (%s, %s, %s, %s, %s)",
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
                "UPDATE runs SET status = %s, updated_at = %s, payload = %s WHERE id = %s",
                (
                    run["status"],
                    run["updated_at"],
                    json.dumps(run, ensure_ascii=False),
                    run["id"],
                ),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE id = %s", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._session() as connection:
            if not connection.execute("SELECT id FROM runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone():
                return False
            connection.execute("DELETE FROM run_ai_reports WHERE run_id = %s", (run_id,))
            cursor = connection.execute("DELETE FROM runs WHERE id = %s", (run_id,))
            return cursor.rowcount > 0

    def system_settings(self) -> dict:
        with self._session() as connection:
            row = connection.execute("SELECT payload FROM system_settings WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else {"default_llm": None}

    def save_system_settings(self, settings: dict) -> dict:
        settings = {**settings, "updated_at": utc_now()}
        with self._session() as connection:
            connection.execute("INSERT INTO system_settings VALUES (1, %s) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(settings),))
        return settings

    def ai_report(self, run_id: str) -> dict:
        with self._session() as connection:
            row = connection.execute("SELECT payload FROM run_ai_reports WHERE run_id=%s", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else {"run_id": run_id, "status": "none", "content": None}

    def begin_ai_report(self, run_id: str, generation_id: str, model: dict) -> dict | None:
        with self._session() as connection:
            if not connection.execute("SELECT id FROM runs WHERE id=%s FOR UPDATE", (run_id,)).fetchone():
                raise ValueError("Run not found")
            row = connection.execute("SELECT payload FROM run_ai_reports WHERE run_id=%s", (run_id,)).fetchone()
            report = json.loads(row["payload"]) if row else {"run_id": run_id, "content": None}
            if report.get("status") == "generating":
                return None
            report.update(status="generating", generation_id=generation_id, requested_at=utc_now(), error=None, requested_model=model)
            connection.execute("INSERT INTO run_ai_reports VALUES (%s, %s) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload", (run_id, json.dumps(report, ensure_ascii=False)))
        return report

    def finish_ai_report(self, run_id: str, generation_id: str, content: str | None, error: str | None = None) -> None:
        with self._session() as connection:
            if not connection.execute("SELECT id FROM runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone():
                return
            row = connection.execute("SELECT payload FROM run_ai_reports WHERE run_id=%s", (run_id,)).fetchone()
            if not row:
                return  # Run/report was deleted while the provider was responding.
            report = json.loads(row["payload"])
            if report.get("generation_id") != generation_id:
                return
            report.update(status="failed" if error else "ready", error=error)
            if not error:
                report.update(content=content, generated_at=utc_now(), model=report["requested_model"])
            connection.execute("UPDATE run_ai_reports SET payload=%s WHERE run_id=%s", (json.dumps(report, ensure_ascii=False), run_id))

    def put_service_config(self, config: dict[str, Any]) -> None:
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO service_configs (id, created_at, updated_at, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload
                """,
                (config["id"], config["created_at"], config["updated_at"], json.dumps(config, ensure_ascii=False)),
            )

    def get_service_config(self, config_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT payload FROM service_configs WHERE id = %s", (config_id,)
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
            cursor = connection.execute("DELETE FROM service_configs WHERE id = %s", (config_id,))
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
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload
                """,
                (plan["id"], plan["created_at"], plan["updated_at"], json.dumps(plan, ensure_ascii=False)),
            )

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT payload FROM test_plans WHERE id = %s", (plan_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_plans(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM test_plans ORDER BY updated_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_plan(self, plan_id: str) -> bool:
        with self._session() as connection:
            cursor = connection.execute("DELETE FROM test_plans WHERE id = %s", (plan_id,))
            return cursor.rowcount > 0

    def active_runs_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs WHERE status IN ('queued', 'running') ORDER BY created_at"
            ).fetchall()
        runs = [json.loads(row["payload"]) for row in rows]
        return [run for run in runs if run.get("plan_id") == plan_id]

    def has_active_run_for_plan(self, plan_id: str) -> bool:
        return bool(self.active_runs_for_plan(plan_id))
