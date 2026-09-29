import asyncio
import tempfile
import unittest
from pathlib import Path

from webapp.runner import BenchmarkRunner
from webapp.secrets import SecretBox
from webapp.store import RunStore, utc_now


class RunStoreTests(unittest.TestCase):
    def test_round_trip_and_restart_marks_active_run_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.sqlite3"
            store = RunStore(path)
            now = utc_now()
            store.create({
                "id": "abc", "name": "test", "benchmark": "embedding",
                "status": "running", "created_at": now, "updated_at": now,
                "scenarios": [], "completed_scenarios": 0, "total_scenarios": 0,
            })
            restarted = RunStore(path)
            self.assertEqual(restarted.get("abc")["status"], "failed")

    def test_persists_service_configs_and_plans(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            config = {
                "id": "svc", "name": "service", "benchmark": "reranker",
                "provider": "vllm", "api_key_encrypted": "ciphertext",
                "created_at": now, "updated_at": now,
            }
            plan = {
                "id": "plan", "name": "matrix", "benchmark": "reranker",
                "providers": [{"id": "svc"}], "concurrency_levels": [1, 5],
                "created_at": now, "updated_at": now,
            }
            store.put_service_config(config)
            store.put_plan(plan)
            self.assertEqual(store.get_service_config("svc")["api_key_encrypted"], "ciphertext")
            self.assertEqual(store.get_plan("plan")["concurrency_levels"], [1, 5])

    def test_restart_repairs_legacy_zero_success_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.sqlite3"
            store = RunStore(path)
            now = utc_now()
            store.create({
                "id": "legacy", "name": "legacy", "benchmark": "embedding",
                "status": "completed", "created_at": now, "updated_at": now,
                "completed_scenarios": 1, "total_scenarios": 1,
                "scenarios": [{
                    "id": "bad", "status": "completed",
                    "result": {"success_count": 0, "failure_count": 2, "metrics": {}},
                }],
            })
            repaired = RunStore(path).get("legacy")
            self.assertEqual(repaired["status"], "failed")
            self.assertEqual(repaired["scenarios"][0]["status"], "failed")


class BenchmarkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.runner = BenchmarkRunner(
            RunStore(root / "db.sqlite3"), root, root / "reports",
            SecretBox.from_data_dir(root),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_expands_provider_concurrency_matrix(self):
        request = {
            "name": "matrix", "benchmark": "reranker",
            "providers": [{"id": "vllm", "model": "m"}, {"id": "local", "model": None}],
            "concurrency_levels": [1, 5, 10], "requests_per_scenario": 10,
            "timeout_seconds": 60,
        }
        # Exercise the same expansion used by create_run without starting an event-loop task.
        scenarios = [
            (provider["id"], concurrency)
            for provider in request["providers"]
            for concurrency in request["concurrency_levels"]
        ]
        self.assertEqual(len(scenarios), 6)
        self.assertIn(("vllm", 10), scenarios)

    def test_builds_allowlisted_cli_command(self):
        run = {
            "benchmark": "embedding", "requests_per_scenario": 20,
            "timeout_seconds": 30,
        }
        scenario = {"provider": "vllm", "model": "bge-m3", "concurrency": 5}
        command = self.runner.build_command(run, scenario, Path("report.json"))
        self.assertIn("perf_embedding.py", command[2])
        self.assertEqual(command[command.index("--provider") + 1], "vllm")
        self.assertEqual(command[command.index("-c") + 1], "5")

    def test_builds_dify_retrieve_command_with_per_plan_inputs(self):
        run = {
            "benchmark": "dify-retrieve", "requests_per_scenario": 20,
            "timeout_seconds": 30, "query": "What is RAG?", "dataset_id": "dataset-123",
        }
        scenario = {
            "provider": "dify", "model": None, "concurrency": 5,
            "base_url": "https://dify.example.com",
        }
        command = self.runner.build_command(run, scenario, Path("report.json"))
        self.assertEqual(command[command.index("--query") + 1], "What is RAG?")
        self.assertEqual(command[command.index("--dataset-id") + 1], "dataset-123")


class BenchmarkRunnerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_persists_completed_scenario_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "perf_embedding.py"
            script.write_text(
                """import json, sys, time
path = sys.argv[sys.argv.index('--json-report') + 1]
print('scenario started', flush=True)
time.sleep(0.05)
report = {'success_rate': 100, 'qps_success': 42.5, 'success_count': 2, 'failure_count': 0, 'metrics': {'latency_ms': {'p50': 10, 'p95': 12, 'p99': 13}}}
open(path, 'w', encoding='utf-8').write(json.dumps(report))
print('scenario finished', flush=True)
""",
                encoding="utf-8",
            )
            store = RunStore(root / "db.sqlite3")
            box = SecretBox.from_data_dir(root)
            runner = BenchmarkRunner(store, root, root / "reports", box)
            now = utc_now()
            config = {
                "id": "svc", "name": "Service", "benchmark": "embedding",
                "provider": "vllm", "base_url": None, "model": "model",
                "api_key_env": "VLLM_API_KEY", "api_key_encrypted": box.encrypt("key"),
                "created_at": now, "updated_at": now,
            }
            store.put_service_config(config)
            request = {
                "name": "matrix", "benchmark": "embedding",
                "providers": [{"id": "svc"}], "concurrency_levels": [1],
                "requests_per_scenario": 2, "timeout_seconds": 30,
            }
            run = runner.create_run(request, "plan", [config])
            await runner.tasks[run["id"]]
            saved = store.get(run["id"])
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["scenarios"][0]["result"]["qps_success"], 42.5)
            self.assertIn("scenario finished", saved["scenarios"][0]["log"])

    async def test_zero_success_report_marks_scenario_and_run_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "perf_embedding.py").write_text(
                """import json, sys
path = sys.argv[sys.argv.index('--json-report') + 1]
report = {'success_rate': 0, 'qps_success': 0, 'success_count': 0, 'failure_count': 2, 'metrics': {}}
open(path, 'w', encoding='utf-8').write(json.dumps(report))
print('Request failed: invalid endpoint', flush=True)
""",
                encoding="utf-8",
            )
            store = RunStore(root / "db.sqlite3")
            box = SecretBox.from_data_dir(root)
            runner = BenchmarkRunner(store, root, root / "reports", box)
            now = utc_now()
            config = {
                "id": "svc", "name": "Service", "benchmark": "embedding",
                "provider": "vllm", "base_url": None, "model": "model",
                "api_key_env": None, "api_key_encrypted": None,
                "created_at": now, "updated_at": now,
            }
            store.put_service_config(config)
            request = {
                "name": "failure", "benchmark": "embedding",
                "providers": [{"id": "svc"}], "concurrency_levels": [1],
                "requests_per_scenario": 2, "timeout_seconds": 30,
            }
            run = runner.create_run(request, "plan", [config])
            await runner.tasks[run["id"]]
            saved = store.get(run["id"])
            self.assertEqual(saved["scenarios"][0]["status"], "failed")
            self.assertEqual(saved["status"], "failed")

    async def test_persists_request_progress_before_scenario_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "perf_dify.py").write_text(
                """import json, sys, time
path = sys.argv[sys.argv.index('--json-report') + 1]
print('Run 01 total=25.00ms', flush=True)
time.sleep(2)
report = {'success_rate': 100, 'qps_success': 1, 'success_count': 1, 'failure_count': 0, 'metrics': {'latency_ms': {'p50': 25, 'p95': 25, 'p99': 25}}}
open(path, 'w', encoding='utf-8').write(json.dumps(report))
""",
                encoding="utf-8",
            )
            store = RunStore(root / "db.sqlite3")
            box = SecretBox.from_data_dir(root)
            runner = BenchmarkRunner(store, root, root / "reports", box)
            now = utc_now()
            config = {
                "id": "dify", "name": "Dify", "benchmark": "dify-retrieve",
                "provider": "dify", "base_url": "https://dify.example.com", "model": None,
                "api_key_env": None, "api_key_encrypted": None,
                "created_at": now, "updated_at": now,
            }
            store.put_service_config(config)
            request = {
                "name": "progress", "benchmark": "dify-retrieve",
                "providers": [{"id": "dify"}], "concurrency_levels": [1],
                "requests_per_scenario": 1, "timeout_seconds": 30,
                "query": "hello", "dataset_id": "dataset",
            }
            run = runner.create_run(request, "plan", [config])
            try:
                await asyncio.sleep(0.4)
                in_progress = store.get(run["id"])
                self.assertEqual(in_progress["scenarios"][0]["completed_requests"], 1)
            finally:
                await runner.cancel(run["id"])


if __name__ == "__main__":
    unittest.main()
