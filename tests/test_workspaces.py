import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from backend import main as web_main
from backend.auth import AuthConfig, AuthService, SESSION_COOKIE
from backend.auth_store import AuthStore
from backend.secrets import SecretBox
from backend.store import TABLE_COLUMNS, utc_now
from backend.tenant_context import WorkspaceProxy, workspace_context
from backend.workspaces import WorkspaceManager
from tests.database import create_test_store


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = create_test_store(self, self.directory)
        self.storage = AuthStore(self.root)
        self.storage.initialize()
        self.secret_box = SecretBox.from_data_dir(self.directory)
        config = AuthConfig(mode="app", public_url="http://testserver", password="fixture-password")
        self.auth = AuthService(config, self.storage, "workspace-test-signing-secret-of-at-least-32-characters")
        self.manager = WorkspaceManager(self.root, web_main.PROJECT_ROOT, self.directory, self.secret_box)
        self.manager.initialize()
        self.auth.workspaces = self.manager
        self.addCleanup(self.drop_workspace_schemas)
        for name, value in (("store", WorkspaceProxy(self.manager, "store")), ("runner", WorkspaceProxy(self.manager, "runner")),
                            ("workspaces", self.manager), ("auth", self.auth), ("secret_box", self.secret_box)):
            replacement = patch.object(web_main, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.app = FastAPI()
        self.auth.install(self.app)
        self.manager.install(self.app)
        self.app.router.routes.extend(route for route in web_main.app.router.routes
                                     if hasattr(route, "path") and not route.path.startswith(("/api/auth/", "/api/workspaces")))
        self.owner, self.owner_status = self.client("github", "100", "owner")
        self.member, self.member_status = self.client("github", "101", "member")
        self.outsider, self.outsider_status = self.client("oidc", "issuer-subject-101", "member")

    def drop_workspace_schemas(self):
        with self.root._session() as connection:
            schemas = connection.execute("SELECT schema_name FROM workspaces WHERE id<>'legacy'").fetchall()
            for row in schemas:
                connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(row["schema_name"])))

    def client(self, provider, subject, username):
        token, user = self.storage.create_session(provider, subject, username, username, self.auth.version)
        client = TestClient(self.app, follow_redirects=False)
        self.addCleanup(client.close)
        client.cookies.set(SESSION_COOKIE, token)
        client.headers.update({"X-CSRF-Token": self.auth.csrf(token), "Origin": "http://testserver"})
        status = client.get("/api/auth/session")
        self.assertEqual(status.status_code, 200, status.text)
        return client, status.json()

    def create_team(self, client=None):
        response = (client or self.owner).post("/api/workspaces", json={"name": "Test team"})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def invite(self, team, inviter=None, username="member", provider="github"):
        response = (inviter or self.owner).post(f"/api/workspaces/{team}/invitations", json={"provider": provider, "username": username})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def join(self, team):
        invitation = self.invite(team)
        response = self.member.post(f"/api/workspaces/invitations/{invitation}/accept")
        self.assertEqual(response.status_code, 200, response.text)
        self.member.headers["X-Workspace-Id"] = team
        return invitation

    def put_fixtures(self, store, name="fixture"):
        now = utc_now()
        store.put_service_config({"id": "config", "name": name, "provider": "vllm", "benchmark": "embedding",
                                  "base_url": "https://models.example/v1/embeddings", "models": ["embedding-model"],
                                  "api_key_encrypted": self.secret_box.encrypt(name + "-secret"),
                                  "created_at": now, "updated_at": now})
        store.put_plan({"id": "plan", "name": name, "created_at": now, "updated_at": now, "status": "paused"})
        store.create({"id": "abcdef123456", "name": name, "status": "completed", "benchmark": "embedding",
                      "created_at": now, "updated_at": now, "scenarios": []})
        store.save_system_settings({"default_llm": {"id": name}})
        store.begin_ai_report("abcdef123456", "generation", {"model": "model"})
        store.finish_ai_report("abcdef123456", "generation", name + " report")

    def test_personal_spaces_are_private_and_legacy_belongs_only_to_local_admin(self):
        self.put_fixtures(self.root, "legacy")
        admin, admin_status = self.client("local", "admin", "admin")
        self.assertEqual(admin_status["personal_workspace_id"], "legacy")
        self.assertEqual(len(admin.get("/api/runs").json()), 1)
        self.assertEqual(self.owner.get("/api/runs").json(), [])
        self.assertEqual(self.member.get("/api/service-configs").json(), [])
        for identifier in ("legacy", self.owner_status["personal_workspace_id"], 'public", public'):
            with self.subTest(workspace=identifier):
                response = self.member.get("/api/runs", headers={"X-Workspace-Id": identifier})
                self.assertEqual(response.status_code, 403)
        self.assertNotEqual(self.member_status["personal_workspace_id"], self.outsider_status["personal_workspace_id"])

    def test_pagination_reaches_all_records_with_stable_order_and_scoped_totals(self):
        team = self.create_team()
        self.join(team)
        self.owner.headers["X-Workspace-Id"] = team
        storage = self.manager.runtime(team).store
        now = utc_now()
        for index in range(125):
            item = {"id": f"{index:012x}", "created_at": now, "updated_at": now,
                    "status": "completed", "name": f"Record {index}", "scenarios": []}
            storage.create(item)
            storage.put_plan({**item, "status": "stopped"})
        expected = [f"{index:012x}" for index in reversed(range(125))]
        for endpoint, legacy_limit in (("runs", 30), ("plans", 100)):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(len(self.owner.get(f"/api/{endpoint}").json()), legacy_limit)
                identifiers = []
                for page in range(1, 4):
                    response = self.member.get(f"/api/{endpoint}?page={page}&page_size=50")
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    self.assertEqual((result["total"], result["page"], result["page_size"]), (125, page, 50))
                    identifiers.extend(item["id"] for item in result["items"])
                    if endpoint == "plans":
                        self.assertTrue(all(item["repeat_mode"] == "once" for item in result["items"]))
                self.assertEqual(identifiers, expected)
                last = self.owner.get(f"/api/{endpoint}?page=999&page_size=50").json()
                self.assertEqual((last["page"], len(last["items"])), (3, 25))
                private = self.owner.get(f"/api/{endpoint}?page=1", headers={"X-Workspace-Id": self.owner_status["personal_workspace_id"]}).json()
                self.assertEqual(private, {"items": [], "total": 0, "page": 1, "page_size": 10})
                self.assertEqual(self.outsider.get(f"/api/{endpoint}?page=1").json()["total"], 0)
                self.assertEqual(self.outsider.get(f"/api/{endpoint}?page=1", headers={"X-Workspace-Id": team}).status_code, 403)

    def test_pagination_validation_empty_and_deletion_clamp(self):
        storage = self.manager.runtime(self.owner_status["personal_workspace_id"]).store
        self.put_fixtures(storage)
        for endpoint, identifier in (("runs", "abcdef123456"), ("plans", "plan")):
            with self.subTest(endpoint=endpoint):
                for query in ("page=0", "page=-1", "page=no", "page=1000000001", "page=1&page_size=0", "page=1&page_size=101"):
                    self.assertEqual(self.owner.get(f"/api/{endpoint}?{query}").status_code, 422)
                result = self.owner.get(f"/api/{endpoint}?page=5&page_size=10").json()
                self.assertEqual((result["total"], result["page"], len(result["items"])), (1, 1, 1))
                self.assertEqual(self.owner.delete(f"/api/{endpoint}/{identifier}").status_code, 204)
                self.assertEqual(self.owner.get(f"/api/{endpoint}?page=5&page_size=10").json(),
                                 {"items": [], "total": 0, "page": 1, "page_size": 10})

    def test_list_search_and_combined_filters_cover_all_pages_and_preserve_isolation(self):
        team = self.create_team()
        self.join(team)
        self.owner.headers["X-Workspace-Id"] = team
        storage = self.manager.runtime(team).store
        now = utc_now()
        for index in range(65):
            item = {"id": f"{index:012x}", "name": f"Alpha 模型 {index}",
                    "plan_id": "linked-needle" if index == 0 else "other-plan",
                    "created_at": now, "updated_at": now, "scenarios": [],
                    "benchmark": "embedding" if index % 3 == 0 else "llm"}
            storage.create({**item, "status": "failed" if index % 2 == 0 else "completed"})
            storage.put_plan({**item, "status": "paused" if index % 2 == 0 else "completed",
                              "repeat_mode": "count" if index % 5 == 0 else "once"})
        for endpoint, params, expected in (
            ("runs", {"status": "failed", "benchmark": "embedding"}, list(reversed(range(0, 65, 6)))),
            ("plans", {"status": "paused", "benchmark": "embedding", "repeat_mode": "count"}, [60, 30, 0]),
        ):
            params = {**params, "q": "  ALPHA 模型  ", "page": 1, "page_size": 2}
            found = []
            for page in range(1, (len(expected) + 1) // 2 + 1):
                response = self.member.get(f"/api/{endpoint}", params={**params, "page": page})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["total"], len(expected))
                found.extend(int(item["id"], 16) for item in result["items"])
            self.assertEqual(found, expected)
            result = self.owner.get(f"/api/{endpoint}", params={**params, "page": 999}).json()
            self.assertEqual(result["page"], (len(expected) + 1) // 2)
            self.assertEqual(self.outsider.get(f"/api/{endpoint}", params=params).json()["total"], 0)
            self.assertEqual(self.outsider.get(f"/api/{endpoint}", params=params, headers={"X-Workspace-Id": team}).status_code, 403)
            self.assertEqual(self.owner.get(f"/api/{endpoint}", params={**params, "status": "completed", "q": "missing-name"}).json()["total"], 0)
            legacy_shape = self.member.get(f"/api/{endpoint}", params={key: value for key, value in params.items() if key not in {"page", "page_size"}}).json()
            self.assertIsInstance(legacy_shape, list)
            self.assertEqual(len(legacy_shape), len(expected))
        self.assertEqual(self.member.get("/api/runs", params={"page": 1, "q": "linked-needle"}).json()["total"], 1)

    def test_list_search_is_literal_and_filters_are_validated(self):
        storage = self.manager.runtime(self.owner_status["personal_workspace_id"]).store
        now = utc_now()
        item = {"id": "literal-id", "name": "Literal %_ 标记", "created_at": now, "updated_at": now, "status": "completed", "scenarios": []}
        storage.create(item)
        storage.put_plan({key: value for key, value in item.items() if key != "status"})
        for endpoint in ("runs", "plans"):
            self.assertEqual(self.owner.get(f"/api/{endpoint}", params={"page": 1, "q": "%_"}).json()["total"], 1)
            self.assertEqual(self.owner.get(f"/api/{endpoint}", params={"page": 1, "q": "' OR 1=1 --"}).json()["total"], 0)
            self.assertEqual(self.owner.get(f"/api/{endpoint}", params={"page": 1, "q": "literal-id"}).json()["total"], 1)
            for invalid in ({"q": "x" * 201}, {"status": "invalid"}, {"benchmark": "invalid"}):
                self.assertEqual(self.owner.get(f"/api/{endpoint}", params={"page": 1, **invalid}).status_code, 422)
        self.assertEqual(self.owner.get("/api/plans", params={"page": 1, "status": "stopped", "repeat_mode": "once"}).json()["total"], 1)
        self.assertEqual(self.owner.get("/api/plans", params={"page": 1, "repeat_mode": "invalid"}).status_code, 422)

    def test_all_data_tables_and_report_directories_are_isolated(self):
        owner_id = self.owner_status["personal_workspace_id"]
        member_id = self.member_status["personal_workspace_id"]
        self.put_fixtures(self.manager.runtime(owner_id).store, "owner")
        self.put_fixtures(self.manager.runtime(member_id).store, "member")
        for client, name in ((self.owner, "owner"), (self.member, "member")):
            self.assertEqual(client.get("/api/runs/abcdef123456").json()["name"], name)
            self.assertEqual(client.get("/api/plans").json()[0]["name"], name)
            self.assertEqual(client.get("/api/service-configs").json()[0]["name"], name)
            self.assertEqual(client.get("/api/system-settings").json()["default_llm"]["id"], name)
            self.assertEqual(client.get("/api/runs/abcdef123456/ai-report").json()["content"], name + " report")
        owner_reports = self.manager.runtime(owner_id).runner.reports_dir / "abcdef123456"
        member_reports = self.manager.runtime(member_id).runner.reports_dir / "abcdef123456"
        owner_reports.mkdir(); member_reports.mkdir()
        (owner_reports / "result.json").write_text("owner")
        (member_reports / "result.json").write_text("member")
        self.assertEqual(self.owner.delete("/api/runs/abcdef123456").status_code, 204)
        self.assertFalse(owner_reports.exists())
        self.assertTrue(member_reports.exists())
        self.assertEqual(self.member.get("/api/runs/abcdef123456").status_code, 200)
        with self.manager.runtime(owner_id).store._session() as connection:
            for table in TABLE_COLUMNS:
                self.assertIsNotNone(connection.execute(f"SELECT * FROM {table} LIMIT 1").description)
            self.assertIsNone(connection.execute("SELECT to_regclass('auth_users') AS table_name").fetchone()["table_name"])

    def test_guessed_ids_cannot_read_mutate_stream_or_reference_other_workspace(self):
        target = self.manager.runtime(self.owner_status["personal_workspace_id"]).store
        self.put_fixtures(target)
        paths = ["/api/runs/abcdef123456", "/api/runs/abcdef123456/ai-report", "/api/runs/abcdef123456/events"]
        for path in paths:
            self.assertEqual(self.member.get(path).status_code, 404)
        self.assertEqual(self.member.delete("/api/runs/abcdef123456").status_code, 404)
        self.assertEqual(self.member.delete("/api/plans/plan").status_code, 404)
        self.assertEqual(self.member.post("/api/runs/abcdef123456/cancel").status_code, 404)
        self.assertEqual(self.member.put("/api/service-configs/config", json={"provider": "vllm", "name": "overwrite"}).status_code, 404)
        response = self.member.post("/api/playground", json={"benchmark": "embedding", "provider_id": "config", "text": "test"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(target.get_service_config("config")["name"], "fixture")

    def test_targeted_invitation_requires_acceptance_and_exact_provider(self):
        team = self.create_team()
        self.assertEqual(self.owner.post(f"/api/workspaces/{team}/invitations", json={"provider": "github", "username": "not-registered"}).status_code, 404)
        invitation = self.invite(team)
        self.assertEqual(self.member.get("/api/runs", headers={"X-Workspace-Id": team}).status_code, 403)
        self.assertEqual(len(self.member.get("/api/workspaces/invitations").json()), 1)
        self.assertEqual(self.outsider.get("/api/workspaces/invitations").json(), [])
        self.assertEqual(self.outsider.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 404)
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 200)
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 409)
        self.assertEqual(self.member.get("/api/runs", headers={"X-Workspace-Id": team}).status_code, 200)
        self.assertEqual(self.outsider.get("/api/runs", headers={"X-Workspace-Id": team}).status_code, 403)
        self.assertEqual(self.member.post(f"/api/workspaces/{team}/invitations", json={"provider": "oidc", "username": "member"}).status_code, 403)

    def test_invitations_expire_can_be_declined_revoked_and_not_privilege_escalated(self):
        team = self.create_team()
        invitation = self.invite(team)
        duplicate = self.owner.post(f"/api/workspaces/{team}/invitations", json={"provider": "github", "username": "member"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.owner.delete(f"/api/workspaces/{team}/invitations/{invitation}").status_code, 204)
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 409)
        invitation = self.invite(team)
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/decline").status_code, 204)
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 409)
        invitation = self.invite(team)
        with self.root._session() as connection:
            connection.execute("UPDATE workspace_invitations SET expires_at=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE id=%s", (invitation,))
        self.assertEqual(self.member.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 409)
        response = self.owner.post(f"/api/workspaces/{team}/invitations", json={"provider": "github", "username": "member", "role": "owner"})
        self.assertEqual(response.status_code, 422)

    def test_owner_admin_member_permissions_and_revocation(self):
        team = self.create_team()
        self.join(team)
        self.put_fixtures(self.manager.runtime(team).store, "team")
        member_id = self.member_status["user"]["id"]
        owner_id = self.owner_status["user"]["id"]
        self.assertEqual(self.member.get("/api/runs").json()[0]["name"], "team")
        self.assertEqual(self.member.get("/api/service-configs").json()[0]["api_key_masked"], "••••••••")
        for method, path, payload in (("put", "/api/system-settings", {"default_llm": None}),
                                     ("post", "/api/service-configs", {}), ("post", "/api/provider-models/list", {}),
                                     ("post", "/api/dify/names", {}), ("delete", "/api/runs/abcdef123456", None),
                                     ("delete", "/api/plans/plan", None)):
            self.assertEqual(self.member.request(method, path, json=payload).status_code, 403)
        self.assertEqual(self.member.patch(f"/api/workspaces/{team}/members/{member_id}", json={"role": "admin"}).status_code, 403)
        self.assertEqual(self.owner.patch(f"/api/workspaces/{team}/members/{member_id}", json={"role": "admin"}).status_code, 200)
        self.assertEqual(self.member.put("/api/system-settings", json={"default_llm": None}).status_code, 200)
        self.assertEqual(self.member.delete(f"/api/workspaces/{team}").status_code, 403)
        self.assertEqual(self.member.delete(f"/api/workspaces/{team}/members/{owner_id}").status_code, 403)
        self.assertEqual(self.member.patch(f"/api/workspaces/{team}/members/{owner_id}", json={"role": "member"}).status_code, 403)
        invitation = self.invite(team, inviter=self.member, provider="oidc")
        self.assertEqual(self.outsider.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 200)
        self.assertEqual(self.owner.delete(f"/api/workspaces/{team}/members/{member_id}").status_code, 204)
        self.assertEqual(self.member.get("/api/runs").status_code, 403)
        self.assertEqual(self.member.get("/api/workspaces").status_code, 200)
        self.assertEqual(self.member.get("/api/runs", headers={"X-Workspace-Id": self.member_status["personal_workspace_id"]}).status_code, 200)

    def test_ownership_is_fixed_and_leave_delete_and_personal_space_are_protected(self):
        team = self.create_team()
        self.join(team)
        member_id = self.member_status["user"]["id"]
        self.assertEqual(self.owner.post(f"/api/workspaces/{team}/leave").status_code, 403)
        for client in (self.owner, self.member, self.outsider):
            self.assertEqual(client.post(f"/api/workspaces/{team}/transfer", json={"user_id": member_id}).status_code, 404)
        for role in ("owner", "admin", "member"):
            self.assertIn(self.owner.patch(f"/api/workspaces/{team}/members/{self.owner_status['user']['id']}", json={"role": role}).status_code, (409, 422))
        self.assertEqual(self.owner.patch(f"/api/workspaces/{team}/members/{member_id}", json={"role": "owner"}).status_code, 422)
        members = self.owner.get(f"/api/workspaces/{team}/members").json()
        self.assertEqual([member["id"] for member in members if member["role"] == "owner"], [self.owner_status["user"]["id"]])
        self.assertEqual(self.member.delete(f"/api/workspaces/{team}").status_code, 403)
        self.assertEqual(self.member.post(f"/api/workspaces/{team}/leave").status_code, 204)
        self.assertEqual(self.owner.post(f"/api/workspaces/{team}/leave").status_code, 403)
        self.assertEqual(self.owner.delete(f"/api/workspaces/{team}").status_code, 204)
        self.assertEqual(self.member.get("/api/runs").status_code, 403)
        self.assertEqual(self.member.get("/api/workspaces").json()["workspaces"][0]["kind"], "personal")
        personal = self.member_status["personal_workspace_id"]
        self.assertEqual(self.member.delete(f"/api/workspaces/{personal}").status_code, 403)
        self.assertEqual(self.member.post(f"/api/workspaces/{personal}/invitations", json={"provider": "github", "username": "owner"}).status_code, 403)

    def test_csrf_and_authentication_protect_team_management(self):
        client = TestClient(self.app)
        self.addCleanup(client.close)
        self.assertEqual(client.post("/api/workspaces", json={"name": "No"}).status_code, 401)
        self.assertEqual(self.member.post("/api/workspaces", json={"name": "No"}, headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        self.assertEqual(self.member.post("/api/workspaces", json={"name": "No"}, headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.owner.post("/api/workspaces", json={"name": "   "}).status_code, 422)

    def test_background_runner_keeps_bound_store_files_and_credentials_after_context_switch(self):
        async def exercise():
            runtime = self.manager.runtime(self.owner_status["personal_workspace_id"])
            self.put_fixtures(runtime.store)
            request = {"name": "runner", "benchmark": "embedding", "providers": [{"id": "config"}], "concurrency_levels": [1],
                       "requests_per_scenario": 1, "timeout_seconds": 10}
            config = {"id": "config", "provider": "vllm", "name": "test", "base_url": "https://models.example/v1/embeddings"}

            def command(run, scenario, report):
                script = "import json,os; from pathlib import Path; Path(" + repr(str(report)) + ").write_text(json.dumps({'success_count':1,'inherited_key':bool(os.getenv('OPENAI_API_KEY'))}))"
                return [sys.executable, "-c", script]

            context_token = workspace_context.set((runtime, {"id": self.owner_status["personal_workspace_id"], "role": "owner"}))
            with patch.object(runtime.runner, "build_command", side_effect=command), patch.dict(os.environ, {"OPENAI_API_KEY": "host-secret-must-not-be-inherited"}):
                run = runtime.runner.create_run(request, "plan", [config])
                workspace_context.reset(context_token)
                switched = workspace_context.set((self.manager.runtime(self.member_status["personal_workspace_id"]), {"id": self.member_status["personal_workspace_id"], "role": "owner"}))
                try:
                    await runtime.runner.tasks[run["id"]]
                finally:
                    workspace_context.reset(switched)
            completed = runtime.store.get(run["id"])
            self.assertEqual(completed["status"], "completed")
            self.assertFalse(completed["scenarios"][0]["result"]["inherited_key"])
            self.assertIsNone(self.manager.runtime(self.member_status["personal_workspace_id"]).store.get(run["id"]))
            self.assertTrue((runtime.runner.reports_dir / run["id"]).is_dir())
        asyncio.run(exercise())

    def test_scheduler_and_ai_report_completion_use_explicit_workspace(self):
        owner_runtime = self.manager.runtime(self.owner_status["personal_workspace_id"])
        member_runtime = self.manager.runtime(self.member_status["personal_workspace_id"])
        self.put_fixtures(owner_runtime.store, "owner")
        self.put_fixtures(member_runtime.store, "member")
        for runtime in (owner_runtime, member_runtime):
            plan = runtime.store.get_plan("plan")
            plan.update(status="active", next_run_at=utc_now())
            runtime.store.put_plan(plan)
        observed = []
        for access in self.manager.scheduled_workspaces():
            context_token = workspace_context.set(access)
            try:
                with patch.object(web_main, "_trigger_scheduled_plan", side_effect=lambda plan: observed.append((access[1]["id"], plan["name"]))):
                    web_main._schedule_workspace_tick(datetime.now(timezone.utc))
            finally:
                workspace_context.reset(context_token)
        self.assertEqual({name for identifier, name in observed}, {"owner", "member"})
        owner_runtime.store.begin_ai_report("abcdef123456", "new-generation", {"model": "model"})
        with patch("backend.ai_reports.generate_report", return_value="owner-only report"):
            web_main._generate_ai_report(owner_runtime.store, owner_runtime.store.get("abcdef123456"), "new-generation", {}, None, "en")
        self.assertEqual(owner_runtime.store.ai_report("abcdef123456")["content"], "owner-only report")
        self.assertEqual(member_runtime.store.ai_report("abcdef123456")["content"], "member report")

    def test_server_environment_keys_are_not_a_tenant_credential_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "host-secret"}):
            self.assertIsNone(web_main._environment_key("OPENAI_API_KEY"))

    def test_member_can_create_and_use_tests_without_config_management(self):
        team = self.create_team()
        self.join(team)
        self.put_fixtures(self.manager.runtime(team).store)
        payload = {"name": "Member plan", "benchmark": "embedding", "providers": [{"id": "config"}], "concurrency_levels": [1], "query": "hello"}
        created = self.member.post("/api/plans", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        identifier = created.json()["id"]
        self.assertEqual(self.member.put(f"/api/plans/{identifier}", json={**payload, "name": "Edited"}).status_code, 200)
        with patch("backend.main.run_playground", return_value={"success": True}) as run:
            response = self.member.post("/api/playground", json={"benchmark": "embedding", "provider_id": "config", "text": "hello"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(run.call_args.args[2], "fixture-secret")

    def test_member_model_catalog_and_settings_are_readable_but_configuration_is_immutable(self):
        team = self.create_team()
        self.join(team)
        runtime = self.manager.runtime(team)
        self.put_fixtures(runtime.store)
        self.owner.headers["X-Workspace-Id"] = team
        catalog = self.member.get("/api/catalog")
        self.assertEqual(catalog.status_code, 200, catalog.text)
        benchmark = next(item for item in catalog.json()["benchmarks"] if item["id"] == "embedding")
        provider = benchmark["providers"][0]
        self.assertEqual(provider["id"], "config")
        self.assertTrue(provider["endpoint_configured"])
        self.assertEqual(provider["models"][0]["name"], "embedding-model")
        self.assertEqual(provider["models"][0]["credentials"][0]["api_key_masked"], "••••••••")
        self.assertNotIn("fixture-secret", catalog.text)
        self.assertNotIn("api_key_encrypted", catalog.text)
        self.assertEqual(self.member.get("/api/system-settings").json(), self.owner.get("/api/system-settings").json())
        original = runtime.store.get_service_config("config")
        settings = runtime.store.system_settings()
        for method, path, payload in (
            ("post", "/api/service-configs", {"name": "Forbidden"}),
            ("put", "/api/service-configs/config", {"name": "Forbidden"}),
            ("delete", "/api/service-configs/config", None),
            ("put", "/api/system-settings", {"default_llm": None}),
            ("post", "/api/provider-models/verify", {}),
            ("post", "/api/provider-models/list", {}),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.member.request(method, path, json=payload).status_code, 403)
        self.assertEqual(runtime.store.get_service_config("config"), original)
        self.assertEqual(runtime.store.system_settings(), settings)
        self.assertEqual(self.outsider.get("/api/catalog", headers={"X-Workspace-Id": team}).status_code, 403)

    def test_existing_event_stream_stops_after_member_removal(self):
        team = self.create_team()
        self.join(team)
        runtime = self.manager.runtime(team)
        self.put_fixtures(runtime.store)
        run = runtime.store.get("abcdef123456")
        run["status"] = "running"
        runtime.store.save(run)

        class EventRequest:
            state = SimpleNamespace(auth_user=self.member_status["user"])
            cookies = {SESSION_COOKIE: self.member.cookies.get(SESSION_COOKIE)}

            async def is_disconnected(self):
                return False

        async def exercise():
            context_token = workspace_context.set((runtime, {"id": team, "role": "member"}))
            try:
                response = await web_main.run_events("abcdef123456", EventRequest())
                event = await anext(response.body_iterator)
                self.assertIn("abcdef123456", event)
                with self.root._session() as connection:
                    connection.execute("DELETE FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (team, self.member_status["user"]["id"]))
                with self.assertRaises(StopAsyncIteration):
                    await anext(response.body_iterator)
            finally:
                workspace_context.reset(context_token)
        asyncio.run(exercise())

    def test_llm_capability_cache_identity_is_workspace_scoped(self):
        from backend.llm_parameters import _identity
        identities = []
        for status in (self.owner_status, self.member_status):
            identifier = status["personal_workspace_id"]
            context_token = workspace_context.set((self.manager.runtime(identifier), {"id": identifier, "role": "owner"}))
            try:
                identities.append(_identity({"provider": "vllm", "base_url": "https://models.example", "model": "model"}, "same-key"))
            finally:
                workspace_context.reset(context_token)
        self.assertNotEqual(identities[0], identities[1])

    def test_personal_space_creation_is_idempotent_under_concurrent_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        token, user = self.storage.create_session("github", "new-concurrent-user", "concurrent", "Concurrent", self.auth.version)
        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(lambda unused: self.manager.ensure_personal(user), range(4)))
        self.assertEqual(len(set(identifiers)), 1)

    def test_provider_balance_is_read_only_and_workspace_scoped(self):
        from backend import provider_balances
        provider_balances._cache.clear()
        team = self.create_team()
        self.join(team)
        self.owner.headers["X-Workspace-Id"] = team
        personal = self.owner_status["personal_workspace_id"]
        now = utc_now()
        for identifier, key in ((team, "team-key"), (personal, "personal-key")):
            self.manager.runtime(identifier).store.put_service_config({"id": "balance-config", "name": "Balance", "provider": "deepseek", "benchmark": "llm", "created_at": now, "updated_at": now, "models": [{"name": "model", "benchmark": "llm", "credentials": [{"id": "credential", "name": "Default", "server_url": "https://api.deepseek.com", "api_key_encrypted": self.secret_box.encrypt(key)}]}]})
        endpoint = "/api/service-configs/balance-config/balance?credential_id=credential"
        with patch("backend.provider_balances._fetch", side_effect=lambda provider, url, key: {"status": "available", "balances": [{"currency": "CNY", "amount": "1" if key == "team-key" else "2"}]}) as fetch:
            self.assertEqual(self.owner.get(endpoint).json()["balances"][0]["amount"], "1")
            member_response = self.member.get(endpoint)
            self.assertEqual(member_response.status_code, 200)
            self.assertNotIn("team-key", member_response.text)
            self.assertEqual(self.owner.get(endpoint, headers={"X-Workspace-Id": personal}).json()["balances"][0]["amount"], "2")
            self.assertEqual(self.outsider.get(endpoint).status_code, 404)
            self.assertEqual(self.outsider.get(endpoint, headers={"X-Workspace-Id": team}).status_code, 403)
            self.assertEqual(fetch.call_count, 2)

    def test_rag_datasets_are_workspace_scoped_and_settings_require_admin(self):
        # Recent FastAPI versions retain included routers as nested route groups;
        # the legacy test harness above copies only routes with a direct path.
        from backend.dataset_routes import install_dataset_routes
        install_dataset_routes(self.app, web_main.store, web_main._playground_access, web_main._dataset_concrete_store)
        team = self.create_team()
        self.join(team)
        self.owner.headers['X-Workspace-Id'] = team
        created = self.member.post('/api/datasets', json={'name': 'Team RAG', 'description': ''})
        self.assertEqual(created.status_code, 201, created.text)
        identifier = created.json()['id']
        path = '/api/datasets/' + identifier
        self.assertEqual(self.owner.get('/api/datasets').json()['total'], 1)
        self.assertEqual(self.member.post(path + '/items', json={'input': 'Question', 'expected_output': 'Answer'}).status_code, 201)
        self.assertEqual(self.owner.get(path + '/items').json()['total'], 1)
        self.assertEqual(self.outsider.get(path).status_code, 404)
        self.assertEqual(self.outsider.get(path, headers={'X-Workspace-Id': team}).status_code, 403)
        self.assertEqual(self.owner.get(path, headers={'X-Workspace-Id': self.owner_status['personal_workspace_id']}).status_code, 404)
        response = self.member.put('/api/dataset-settings', json={'prompt': 'Member prompt'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.owner.put('/api/dataset-settings', json={'prompt': 'Team prompt'}).status_code, 200)
        self.assertEqual(self.member.get('/api/dataset-settings').json()['prompt'], 'Team prompt')
        self.assertNotEqual(self.outsider.get('/api/dataset-settings').json()['prompt'], 'Team prompt')
        self.assertEqual(self.owner.put('/api/system-settings', json={'default_llm': None}).status_code, 200)
        self.assertEqual(self.member.get('/api/dataset-settings').json()['prompt'], 'Team prompt')
