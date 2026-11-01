import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend import main
from backend.migrate_sqlite import migrate_sqlite
from backend.secrets import SecretBox
from backend.store import TABLE_COLUMNS, RunStore, utc_now
from tests.database import create_test_store


class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = create_test_store(self, self.root / "database")
        now = utc_now()
        self.run = {"id": "run", "status": "completed", "created_at": now,
                    "updated_at": now, "scenarios": []}

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaisesRegex(ValueError, "abort"):
            with self.store._session() as connection:
                connection.execute("INSERT INTO system_settings VALUES (1, %s)", ('{"default_llm": "temporary"}',))
                raise ValueError("abort")
        self.assertEqual(self.store.system_settings(), {"default_llm": None})

    def test_concurrent_report_requests_have_one_winner(self):
        self.store.create(self.run)
        barrier = threading.Barrier(8)

        def begin(index):
            barrier.wait(timeout=10)
            return self.store.begin_ai_report("run", str(index), {"model": "模型"})

        with ThreadPoolExecutor(max_workers=8) as executor:
            reports = list(executor.map(begin, range(8)))
        winners = [report for report in reports if report is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.store.ai_report("run")["generation_id"], winners[0]["generation_id"])

    def test_delete_and_finish_cannot_resurrect_report(self):
        self.store.create(self.run)
        self.store.begin_ai_report("run", "generation", {"model": "模型"})
        barrier = threading.Barrier(2)

        def finish():
            barrier.wait(timeout=10)
            self.store.finish_ai_report("run", "generation", "报告")

        def delete():
            barrier.wait(timeout=10)
            return self.store.delete_run("run")

        with ThreadPoolExecutor(max_workers=2) as executor:
            finished = executor.submit(finish)
            deleted = executor.submit(delete)
            finished.result(timeout=15)
            self.assertTrue(deleted.result(timeout=15))
        self.assertIsNone(self.store.get("run"))
        self.assertEqual(self.store.ai_report("run")["status"], "none")

    def test_lifespan_initializes_storage(self):
        with patch.object(main, "root_store", self.store), patch.object(self.store, "initialize", wraps=self.store.initialize) as initialize:
            async def start():
                async with main.lifespan(main.app):
                    initialize.assert_called_once_with()
            asyncio.run(start())

    def legacy_database(self, *, optional_tables=True):
        source = self.root / "legacy.sqlite3"
        box = SecretBox.from_data_dir(self.root)
        now = utc_now()
        self.config = {"id": "service", "created_at": now, "updated_at": now,
                       "name": "中文服务", "api_key_encrypted": box.encrypt("original-key")}
        self.plan = {"id": "plan", "created_at": now, "updated_at": now, "name": "测试计划"}
        self.report = {"run_id": "run", "status": "ready", "content": "分析报告"}
        payloads = {"runs": self.run, "service_configs": self.config, "test_plans": self.plan,
                    "system_settings": {"id": 1, "default_llm": None}, "run_ai_reports": self.report}
        with sqlite3.connect(source) as connection:
            for table, columns in TABLE_COLUMNS.items():
                if not optional_tables and table in {"system_settings", "run_ai_reports"}:
                    continue
                definitions = ", ".join(f"{column} TEXT" for column in columns)
                connection.execute(f"CREATE TABLE {table} ({definitions})")
                values = [json.dumps(payloads[table], ensure_ascii=False) if column == "payload" else payloads[table][column]
                          for column in columns]
                connection.execute(f"INSERT INTO {table} VALUES ({', '.join(['?'] * len(columns))})", values)
        return source, box

    def test_migration_preserves_all_tables_secrets_and_source(self):
        source, box = self.legacy_database()
        original = source.read_bytes()
        counts = migrate_sqlite(source, self.store.database_url)
        self.assertEqual(counts, dict.fromkeys(TABLE_COLUMNS, 1))
        self.assertEqual(self.store.get("run"), self.run)
        self.assertEqual(self.store.get_plan("plan"), self.plan)
        self.assertEqual(self.store.get_service_config("service"), self.config)
        self.assertEqual(box.decrypt(self.store.get_service_config("service")["api_key_encrypted"]), "original-key")
        self.assertEqual(self.store.ai_report("run"), self.report)
        self.assertEqual(self.store.system_settings(), {"id": 1, "default_llm": None})
        self.assertEqual(source.read_bytes(), original)
        reopened = RunStore(self.store.database_url)
        self.assertEqual(reopened.get_plan("plan"), self.plan)

    def test_migration_rejects_nonempty_target(self):
        source, _ = self.legacy_database()
        settings = self.store.save_system_settings({"default_llm": "keep"})
        with self.assertRaisesRegex(ValueError, "must be empty"):
            migrate_sqlite(source, self.store.database_url)
        self.assertEqual(self.store.system_settings(), settings)
        self.assertEqual(self.store.list(), [])

    def test_migration_failure_rolls_back_partial_import(self):
        source, _ = self.legacy_database()
        with sqlite3.connect(source) as connection:
            connection.execute("UPDATE test_plans SET payload = 'invalid-json'")
        with self.assertRaises(json.JSONDecodeError):
            migrate_sqlite(source, self.store.database_url)
        for table in TABLE_COLUMNS:
            with self.store._session() as connection:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"], 0)

    def test_migration_accepts_legacy_workspace_without_optional_tables(self):
        source, _ = self.legacy_database(optional_tables=False)
        counts = migrate_sqlite(source, self.store.database_url)
        self.assertEqual(counts["system_settings"], 0)
        self.assertEqual(counts["run_ai_reports"], 0)
        self.assertEqual(self.store.get_plan("plan"), self.plan)

    def test_migration_rejects_missing_or_unrelated_source(self):
        source = self.root / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            migrate_sqlite(source, self.store.database_url)
        self.assertFalse(source.exists())
        with sqlite3.connect(source):
            pass
        with self.assertRaisesRegex(ValueError, "not a PrismLab"):
            migrate_sqlite(source, self.store.database_url)
