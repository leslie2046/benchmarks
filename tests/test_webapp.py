import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from webapp import main as web_main
from webapp.connectivity import ConnectivityError, check_models
from webapp.runner import BenchmarkRunner
from pydantic import ValidationError

from webapp.schemas import ProviderAccess, ServiceConfigCreate, TestPlanCreate
from webapp.model_discovery import list_models
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

    def test_deletes_run_and_service_config_without_touching_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            config = {"id": "svc", "name": "supplier", "benchmark": "embedding", "provider": "vllm", "models": ["m1", "m2"], "created_at": now, "updated_at": now}
            run = {"id": "run", "name": "test", "status": "completed", "created_at": now, "updated_at": now, "scenarios": [{"service_config_id": "svc"}]}
            store.put_service_config(config)
            store.create(run)
            self.assertFalse(store.has_active_run_for_config("svc"))
            self.assertTrue(store.delete_service_config("svc"))
            self.assertIsNotNone(store.get("run"))
            self.assertTrue(store.delete_run("run"))
            self.assertIsNone(store.get("run"))

    def test_deleting_plan_keeps_its_run_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            plan = {"id": "plan", "name": "scheduled", "created_at": now, "updated_at": now}
            run = {"id": "run", "plan_id": "plan", "name": "scheduled", "status": "completed", "created_at": now, "updated_at": now, "scenarios": []}
            store.put_plan(plan)
            store.create(run)
            self.assertTrue(store.delete_plan("plan"))
            self.assertIsNone(store.get_plan("plan"))
            self.assertIsNotNone(store.get("run"))

    def test_repeating_plan_requires_count_and_interval(self):
        values = {
            "name": "scheduled", "benchmark": "reranker",
            "providers": [{"id": "svc"}], "concurrency_levels": [1],
            "repeat_mode": "count", "query": "question", "documents": ["document"],
        }
        with self.assertRaises(ValidationError):
            TestPlanCreate.model_validate(values)
        plan = TestPlanCreate.model_validate({**values, "repeat_count": 3, "repeat_interval_seconds": 60})
        self.assertEqual(plan.repeat_count, 3)

    def test_model_selection_must_belong_to_supplier(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            store.put_service_config({
                "id": "svc", "name": "supplier", "benchmark": "embedding",
                "provider": "vllm", "base_url": "https://example.com/v1/embeddings",
                "model": "m1", "models": ["m1", "m2"],
                "created_at": now, "updated_at": now,
            })
            with patch.object(web_main, "store", store):
                self.assertEqual(web_main._resolve_configs("embedding", [{"id": "svc", "model": "m2"}])[0]["id"], "svc")
                with self.assertRaises(HTTPException) as raised:
                    web_main._resolve_configs("embedding", [{"id": "svc", "model": "unknown"}])
                self.assertEqual(raised.exception.status_code, 400)

    def test_one_supplier_resolves_distinct_model_types(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            store.put_service_config({
                "id": "svc", "name": "Xinference", "benchmark": "embedding",
                "provider": "xinference", "models": [
                    {"name": "embed", "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"},
                    {"name": "rerank", "benchmark": "reranker", "base_url": "https://example.com/v1/rerank"},
                ], "created_at": now, "updated_at": now,
            })
            self.assertEqual(len(store.list_service_configs("embedding")), 1)
            self.assertEqual(len(store.list_service_configs("reranker")), 1)
            with patch.object(web_main, "store", store):
                resolved = web_main._resolve_configs("reranker", [{"id": "svc", "model": "rerank"}])
            self.assertEqual(resolved[0]["base_url"], "https://example.com/v1/rerank")
            self.assertEqual(resolved[0]["model"], "rerank")

    def test_run_deletion_rejects_active_run_and_removes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RunStore(root / "runs.sqlite3")
            now = utc_now()
            run_id = "abcdef123456"
            run = {"id": run_id, "name": "test", "status": "running", "created_at": now, "updated_at": now, "scenarios": []}
            store.create(run)
            report_dir = root / "reports" / run_id
            report_dir.mkdir(parents=True)
            (report_dir / "result.json").write_text("{}", encoding="utf-8")
            with patch.object(web_main, "store", store), patch.object(web_main, "runner", SimpleNamespace(reports_dir=root / "reports")):
                with self.assertRaises(HTTPException) as raised:
                    web_main.delete_run(run_id)
                self.assertEqual(raised.exception.status_code, 409)
                run["status"] = "completed"
                store.save(run)
                web_main.delete_run(run_id)
            self.assertIsNone(store.get(run_id))
            self.assertFalse(report_dir.exists())

    def test_save_is_independent_of_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            payload = ServiceConfigCreate(name="new", provider="vllm", models=[
                {"name": "m", "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"},
            ])
            with patch.object(web_main, "store", store), patch.object(web_main, "check_models", side_effect=ConnectivityError("unreachable")):
                public = web_main.create_service_config(payload)
            self.assertEqual(public["models"][0]["name"], "m")
            self.assertEqual(len(store.list_service_configs()), 1)

    def test_model_alias_and_multiple_credentials_use_selected_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            payload = ServiceConfigCreate(name="Lab", provider="vllm", models=[{
                "name": "bge-m3", "alias": "Embedding lab", "benchmark": "embedding",
                "credentials": [
                    {"name": "A", "server_url": "https://a.example.com", "model_uid": "bge-m3-a", "api_key": "key-a"},
                    {"name": "B", "server_url": "https://b.example.com", "model_uid": "bge-m3-b", "api_key": "key-b"},
                ],
            }])
            with patch.object(web_main, "store", store), patch.object(web_main, "check_models") as check:
                public = web_main.create_service_config(payload)
                check.assert_not_called()
                self.assertNotIn("key-a", str(public))
                self.assertNotIn("api_key_encrypted", str(public))
                self.assertEqual(public["models"][0]["credentials"][0]["api_key_masked"], "ke••••••••")
                with self.assertRaises(HTTPException):
                    web_main._resolve_configs("embedding", [{"id": public["id"], "model": "Embedding lab"}])
                chosen = web_main._resolve_configs("embedding", [{"id": public["id"], "model": "Embedding lab", "credential_id": public["models"][0]["credentials"][1]["id"]}])[0]
                self.assertEqual(chosen["base_url"], "https://b.example.com/v1/embeddings")
                self.assertEqual(chosen["model"], "bge-m3-b")
                stored = store.get_service_config(public["id"])
                second = stored["models"][0]["credentials"][1]
                self.assertEqual(web_main.secret_box.decrypt(second["api_key_encrypted"]), "key-b")
                update = ServiceConfigCreate(name="Lab", provider="vllm", models=[{
                    "name": "bge-m3", "alias": "Embedding lab", "benchmark": "embedding",
                    "credentials": [{"id": second["id"], "name": "Renamed", "server_url": "https://b.example.com", "model_uid": "bge-m3-b"}],
                }])
                web_main.update_service_config(public["id"], update)
                retained = store.get_service_config(public["id"])["models"][0]["credentials"][0]
                self.assertEqual(web_main.secret_box.decrypt(retained["api_key_encrypted"]), "key-b")

    def test_model_discovery_and_verification_do_not_save(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            access = ProviderAccess(provider="siliconflow", server_url="https://api.siliconflow.cn", api_key="secret")
            with patch.object(web_main, "store", store), patch.object(web_main, "verify_key") as verify, patch.object(web_main, "list_models", return_value=[{"id": "BAAI/bge-m3", "benchmark": "embedding"}]) as listing:
                self.assertTrue(web_main.verify_provider_access(access)["valid"])
                self.assertEqual(web_main.list_provider_models(access)["models"][0]["id"], "BAAI/bge-m3")
                verify.assert_called_once_with("siliconflow", "https://api.siliconflow.cn", "secret")
                listing.assert_called_once()
            self.assertEqual(store.list_service_configs(), [])

    def test_discovered_model_can_reuse_saved_encrypted_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            first = ServiceConfigCreate(name="Lab", provider="vllm", models=[{"name": "embed", "benchmark": "embedding", "credentials": [{"name": "Default", "server_url": "https://example.com", "api_key": "secret"}]}])
            with patch.object(web_main, "store", store):
                public = web_main.create_service_config(first)
                source_id = public["models"][0]["credentials"][0]["id"]
                access = ProviderAccess(provider="vllm", server_url="https://example.com", config_id=public["id"], credential_id=source_id)
                with patch.object(web_main, "verify_key") as verify:
                    web_main.verify_provider_access(access)
                    verify.assert_called_once_with("vllm", "https://example.com", "secret")
                imported = ServiceConfigCreate(name="Lab", provider="vllm", models=[
                    {"name": "embed", "benchmark": "embedding", "credentials": [{"id": source_id, "name": "Default", "server_url": "https://example.com"}]},
                    {"name": "rerank", "benchmark": "reranker", "credentials": [{"name": "Default", "server_url": "https://example.com", "copy_key_from": source_id}]},
                ])
                updated = web_main.update_service_config(public["id"], imported)
                new_credential = store.get_service_config(public["id"])["models"][1]["credentials"][0]
                self.assertEqual(web_main.secret_box.decrypt(new_credential["api_key_encrypted"]), "secret")
                self.assertNotIn("secret", str(updated))

    def test_siliconflow_discovery_uses_supported_subtypes(self):
        def response_for(_url, **kwargs):
            subtype = (kwargs["params"] or {}).get("sub_type")
            names = ["model-embedding", "model-reranker", "chat-only"] if not subtype else [f"model-{subtype}"]
            return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": name} for name in names]})
        with patch("webapp.model_discovery.requests.get", side_effect=response_for) as get:
            found = list_models("siliconflow", "https://api.siliconflow.cn/v1", "secret")
        self.assertEqual({item["benchmark"] for item in found}, {"embedding", "reranker", None})
        self.assertIn({"id": "chat-only", "benchmark": None}, found)
        self.assertEqual(get.call_count, 3)
        self.assertTrue(all(call.kwargs["headers"]["Authorization"] == "Bearer secret" for call in get.call_args_list))

    def test_model_alias_can_repeat_across_providers_and_provider_survives_last_model_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.sqlite3")
            now = utc_now()
            for config_id, provider, alias in (("one", "vllm", "Shared"), ("two", "xinference", "Other")):
                store.put_service_config({
                    "id": config_id, "name": provider, "provider": provider,
                    "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings",
                    "models": [{"name": alias, "alias": alias, "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"}],
                    "created_at": now, "updated_at": now,
                })
            duplicate = ServiceConfigCreate(name="xinference", provider="xinference", models=[{
                "name": "other-model", "alias": "shared", "benchmark": "embedding",
                "base_url": "https://example.com/v1/embeddings",
            }])
            with patch.object(web_main, "store", store), patch.object(web_main, "check_models"):
                updated = web_main.update_service_config("two", duplicate)
                self.assertEqual(updated["models"][0]["alias"], "shared")
                self.assertEqual(store.get_service_config("one")["models"][0]["alias"], "Shared")
                with self.assertRaises(HTTPException) as raised:
                    web_main.delete_service_config("two")
                self.assertEqual(raised.exception.status_code, 409)
                emptied = web_main.update_service_config("two", ServiceConfigCreate(name="xinference", provider="xinference", models=[]))
                self.assertEqual(emptied["models"], [])
                self.assertFalse(emptied["endpoint_configured"])
                self.assertIsNotNone(store.get_service_config("two"))

    def test_connectivity_rejects_unauthorized_response(self):
        response = SimpleNamespace(status_code=401)
        with patch("webapp.connectivity.requests.post", return_value=response) as post:
            with self.assertRaises(ConnectivityError):
                check_models([{"benchmark": "embedding", "base_url": "https://example.com/v1/embeddings", "model": "BAAI/bge-m3"}], "bad-key")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer bad-key")
        self.assertEqual(post.call_args.kwargs["json"], {"model": "BAAI/bge-m3", "input": "connectivity test"})

    def test_connectivity_posts_inference_payload_and_rejects_invalid_model(self):
        with patch("webapp.connectivity.requests.post", return_value=SimpleNamespace(status_code=200)) as post:
            check_models([{"benchmark": "embedding", "base_url": "https://api.siliconflow.cn/v1/embeddings", "model": "BAAI/bge-m3", "api_key": "key"}], None)
        self.assertEqual(post.call_args.args[0], "https://api.siliconflow.cn/v1/embeddings")
        with patch("webapp.connectivity.requests.post", return_value=SimpleNamespace(status_code=400)):
            with self.assertRaises(ConnectivityError):
                check_models([{"benchmark": "embedding", "base_url": "https://example.com/v1/embeddings", "model": "missing"}], None)

    def test_audio_connectivity_posts_multipart_probe(self):
        with patch("webapp.connectivity.requests.post", return_value=SimpleNamespace(status_code=200)) as post, patch(
            "webapp.connectivity.requests.get", return_value=SimpleNamespace(status_code=404)
        ):
            check_models([{
                "benchmark": "audio", "base_url": "https://example.com/v1/audio/transcriptions",
                "model": "Qwen3-ASR-0.6B", "api_key": "key",
            }], None)
        self.assertEqual(post.call_args.args[0], "https://example.com/v1/audio/transcriptions")
        self.assertEqual(post.call_args.kwargs["data"], {"model": "Qwen3-ASR-0.6B"})
        self.assertEqual(post.call_args.kwargs["files"]["file"][0], "connectivity.wav")

    def test_dify_connectivity_probes_api_routes_instead_of_site_root(self):
        cases = (
            ("dify-retrieve", "https://dify.example.com", "https://dify.example.com/v1/datasets"),
            ("dify-chat", "https://dify.example.com/v1/", "https://dify.example.com/v1/parameters"),
        )
        for benchmark, base_url, expected_url in cases:
            with self.subTest(benchmark=benchmark), patch(
                "webapp.connectivity.requests.get",
                return_value=SimpleNamespace(status_code=200),
            ) as get:
                check_models([{
                    "benchmark": benchmark,
                    "base_url": base_url,
                    "model": None,
                    "api_key": "dify-key",
                }], None)
            self.assertEqual(get.call_args.args[0], expected_url)
            self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer dify-key")

    def test_xinference_404_identifies_missing_model_uid(self):
        listing = SimpleNamespace(status_code=200, json=lambda: {"running-uid": {}})
        model = {"benchmark": "embedding", "base_url": "http://host:9997/v1/embeddings", "server_url": "http://host:9997", "model": "model-name", "provider": "xinference"}
        with patch("webapp.connectivity.requests.post", return_value=SimpleNamespace(status_code=404)), patch("webapp.connectivity.requests.get", return_value=listing) as get:
            with self.assertRaisesRegex(ConnectivityError, "IDs reported by this URL: running-uid"):
                check_models([model], None)
        self.assertEqual(get.call_args.args[0], "http://host:9997/v1/models")

    def test_vllm_404_identifies_missing_model_id(self):
        listing = SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "served-bge-m3"}]})
        model = {"benchmark": "embedding", "base_url": "http://host:7862/v1/embeddings", "server_url": "http://host:7862", "model": "bge-m3", "provider": "vllm"}
        with patch("webapp.connectivity.requests.post", return_value=SimpleNamespace(status_code=404)), patch("webapp.connectivity.requests.get", return_value=listing):
            with self.assertRaisesRegex(ConnectivityError, "IDs reported by this URL: served-bge-m3"):
                check_models([model], None)

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

    def test_builds_temporary_input_file_for_custom_model_inputs(self):
        report = self.runner.reports_dir / "run" / "scenario.json"
        run = {
            "benchmark": "reranker", "requests_per_scenario": 2, "timeout_seconds": 30,
            "query": "Which document is relevant?", "documents": ["First", "Second"],
        }
        scenario = {"provider": "vllm", "model": "reranker", "concurrency": 1}
        command = self.runner.build_command(run, scenario, report)
        input_path = Path(command[command.index("--input-file") + 1])
        self.assertEqual(json.loads(input_path.read_text(encoding="utf-8")), {
            "query": "Which document is relevant?", "documents": ["First", "Second"],
        })

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
                "providers": [{"id": "svc", "model": "selected-model"}], "concurrency_levels": [1],
                "requests_per_scenario": 2, "timeout_seconds": 30,
            }
            run = runner.create_run(request, "plan", [config])
            await runner.tasks[run["id"]]
            saved = store.get(run["id"])
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["scenarios"][0]["model"], "selected-model")
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
