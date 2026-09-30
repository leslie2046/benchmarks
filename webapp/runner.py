import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from webapp.store import RunStore, utc_now
from webapp.secrets import SecretBox


class BenchmarkRunner:
    def __init__(self, store: RunStore, project_root: Path, reports_dir: Path, secret_box: SecretBox):
        self.store = store
        self.project_root = project_root
        self.reports_dir = reports_dir
        self.secret_box = secret_box
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, asyncio.Task] = {}
        self.processes: dict[str, asyncio.subprocess.Process] = {}

    def create_run(self, request: dict[str, Any], plan_id: str, configs: list[dict]) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        now = utc_now()
        scenarios = [
            {
                "id": f"{config['id']}-c{concurrency}",
                "service_config_id": config["id"],
                "credential_id": config.get("credential_id"),
                "provider": config["provider"],
                "provider_name": config["name"],
                "base_url": config.get("base_url"),
                "model": config.get("model") if config.get("model_selected") else next((item.get("model") for item in request["providers"] if item["id"] == config["id"]), None) or config.get("model"),
                "api_key_env": config.get("api_key_env"),
                "concurrency": concurrency,
                "status": "queued",
                "completed_requests": 0,
                "total_requests": request["requests_per_scenario"],
                "result": None,
                "error": None,
            }
            for config in configs
            for concurrency in request["concurrency_levels"]
        ]
        run = {
            "id": run_id,
            "plan_id": plan_id,
            **request,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "completed_scenarios": 0,
            "total_scenarios": len(scenarios),
            "scenarios": scenarios,
            "error": None,
        }
        self.store.create(run)
        self.tasks[run_id] = asyncio.create_task(self._execute(run_id))
        return run

    async def cancel(self, run_id: str) -> bool:
        task = self.tasks.get(run_id)
        if not task or task.done():
            return False
        process = self.processes.get(run_id)
        if process and process.returncode is None:
            process.terminate()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        run = self.store.get(run_id)
        if run:
            run["status"] = "cancelled"
            run["finished_at"] = utc_now()
            for scenario in run["scenarios"]:
                if scenario["status"] == "running":
                    scenario["status"] = "cancelled"
            self.store.save(run)
        return True

    async def _execute(self, run_id: str) -> None:
        run = self.store.get(run_id)
        if not run:
            return
        run["status"] = "running"
        run["started_at"] = utc_now()
        self.store.save(run)
        try:
            for index, scenario in enumerate(run["scenarios"]):
                scenario["status"] = "running"
                scenario["started_at"] = utc_now()
                self.store.save(run)
                report_path = self.reports_dir / run_id / f"{scenario['id']}.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                command = self.build_command(run, scenario, report_path)
                process_env = os.environ.copy()
                service_config = self.store.get_service_config(scenario["service_config_id"])
                if service_config and scenario.get("api_key_env"):
                    api_key = None
                    if scenario.get("credential_id"):
                        from webapp.model_configs import configured_models
                        api_key = next((self.secret_box.decrypt(c.get("api_key_encrypted")) for model in configured_models(service_config) for c in model.get("credentials", []) if c["id"] == scenario["credential_id"]), None)
                    if not api_key:
                        api_key = self.secret_box.decrypt(service_config.get("api_key_encrypted"))
                    if api_key:
                        process_env[scenario["api_key_env"]] = api_key
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=self.project_root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=process_env,
                )
                self.processes[run_id] = process
                log = ""
                last_saved = asyncio.get_running_loop().time()
                assert process.stdout is not None
                while line := await process.stdout.readline():
                    decoded = line.decode("utf-8", errors="replace")
                    log = (log + decoded)[-8000:]
                    scenario["log"] = log
                    progress_match = re.match(r"Run\s+(\d+)", decoded.strip())
                    if progress_match:
                        scenario["completed_requests"] = max(
                            scenario["completed_requests"], int(progress_match.group(1))
                        )
                        self.store.save(run)
                        last_saved = asyncio.get_running_loop().time()
                        continue
                    now = asyncio.get_running_loop().time()
                    if now - last_saved >= 0.5:
                        self.store.save(run)
                        last_saved = now
                await process.wait()
                scenario["log"] = log
                if report_path.exists():
                    scenario["result"] = json.loads(report_path.read_text(encoding="utf-8"))
                has_successes = bool(
                    scenario["result"] and scenario["result"].get("success_count", 0) > 0
                )
                if process.returncode == 0 and has_successes:
                    scenario["status"] = "completed"
                else:
                    scenario["status"] = "failed"
                    scenario["error"] = (
                        "No requests succeeded; check the Endpoint, credentials, model and server logs"
                        if scenario["result"] and not has_successes
                        else self._last_log_line(log) or f"Exited with {process.returncode}"
                    )
                scenario["finished_at"] = utc_now()
                run["completed_scenarios"] = index + 1
                self.store.save(run)
            run["status"] = (
                "completed"
                if any(item["status"] == "completed" for item in run["scenarios"])
                else "failed"
            )
            if run["status"] == "failed":
                run["error"] = "All benchmark scenarios failed"
            run["finished_at"] = utc_now()
            self.store.save(run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)
            run["finished_at"] = utc_now()
            self.store.save(run)
        finally:
            self.processes.pop(run_id, None)

    def build_command(self, run: dict, scenario: dict, report_path: Path) -> list[str]:
        benchmark = run["benchmark"]
        common = [
            "-c", str(scenario["concurrency"]),
            "-n", str(run["requests_per_scenario"]),
            "--timeout", str(run["timeout_seconds"]),
            "--json-report", str(report_path),
        ]
        if benchmark in {"embedding", "reranker"}:
            script = self.project_root / f"perf_{benchmark}.py"
            command = [sys.executable, "-u", str(script), "--provider", scenario["provider"], *common]
            if scenario.get("model"):
                command.extend(["--model", scenario["model"]])
            if scenario.get("base_url"):
                command.extend(["--base-url", scenario["base_url"]])
            return command
        if benchmark == "audio":
            command = [sys.executable, "-u", str(self.project_root / "perf_audio.py"), *common]
            if scenario.get("model"):
                command.extend(["--model", scenario["model"]])
            if scenario.get("base_url"):
                command.extend(["--base-url", scenario["base_url"]])
            return command
        if benchmark in {"dify-retrieve", "dify-chat"}:
            mode = benchmark.split("-", 1)[1]
            command = [sys.executable, "-u", str(self.project_root / "perf_dify.py"), mode, *common]
            if scenario.get("base_url"):
                command.extend(["--base-url", scenario["base_url"]])
            if run.get("query"):
                command.extend(["--query", run["query"]])
            if benchmark == "dify-retrieve" and run.get("dataset_id"):
                command.extend(["--dataset-id", run["dataset_id"]])
            return command
        raise ValueError(f"Unsupported benchmark: {benchmark}")

    @staticmethod
    def _last_log_line(log: str) -> str | None:
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        return lines[-1][:500] if lines else None
