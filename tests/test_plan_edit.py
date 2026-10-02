import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from backend import main
from backend.schemas import TestPlanCreate
from backend.store import RunStore, utc_now


class PlanEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RunStore(Path(self.temp.name) / "runs.sqlite3")
        self.addCleanup(patch.stopall)
        patch.object(main, "store", self.store).start()
        now = utc_now()
        self.store.put_service_config({
            "id": "svc", "name": "supplier", "benchmark": "embedding",
            "provider": "vllm", "base_url": "https://example.com/v1/embeddings",
            "model": "m1", "models": ["m1", "m2"], "created_at": now, "updated_at": now,
        })
        self.payload = TestPlanCreate(name="original", benchmark="embedding", query="original query",
                                      providers=[{"id": "svc", "model": "m1"}], concurrency_levels=[1])
        self.plan = main.create_plan(self.payload)
        self.plan.update(status="completed", run_count=4, schedule_run_count=4, last_run_id="old",
                         last_run_at=now, schedule_error="old error")
        self.store.put_plan(self.plan)
        self.run = {"id": "old", "plan_id": self.plan["id"], "name": "original", "query": "original query",
                    "status": "completed", "created_at": now, "updated_at": now, "scenarios": []}
        self.store.create(self.run)

    def update(self, **changes):
        payload = TestPlanCreate(**(self.payload.model_dump() | changes))
        return asyncio.run(main.update_plan(self.plan["id"], payload))

    def test_edit_preserves_history_and_restarts_schedule_only(self):
        updated = self.update(name="updated", query="new query", providers=[{"id": "svc", "model": "m2"}],
                              concurrency_levels=[2, 7], repeat_mode="count", repeat_count=3,
                              repeat_interval_seconds=3600, start_at="2026-12-01T01:00:00Z")
        self.assertEqual(updated["id"], self.plan["id"])
        self.assertEqual(updated["created_at"], self.plan["created_at"])
        self.assertEqual(updated["status"], "paused")
        self.assertEqual(updated["run_count"], 4)
        self.assertEqual(updated["schedule_run_count"], 0)
        self.assertEqual(updated["last_run_id"], "old")
        self.assertIsNone(updated["schedule_error"])
        self.assertEqual(updated["next_run_at"], updated["start_at"])
        self.assertEqual(self.store.get(self.run["id"]), self.run)
        self.assertEqual(self.store.get_plan(updated["id"])["query"], "new query")
        self.assertEqual(main._plan_request(updated)["providers"][0]["model"], "m2")

    def test_active_plan_and_unfinished_runs_cannot_be_edited(self):
        for status in ("active", "paused"):
            for run_status in ("running", "queued"):
                with self.subTest(status=status, run_status=run_status):
                    self.plan["status"] = status
                    self.store.put_plan(self.plan)
                    self.store.save({**self.run, "status": run_status})
                    with self.assertRaises(HTTPException) as error:
                        self.update(name="blocked")
                    self.assertEqual(error.exception.status_code, 409)
                    self.assertEqual(self.store.get_plan(self.plan["id"])["name"], "original")

    def test_missing_plan_and_invalid_model_do_not_write(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.update_plan("missing", self.payload))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as error:
            self.update(providers=[{"id": "svc", "model": "missing"}])
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.store.get_plan(self.plan["id"]), self.plan)
