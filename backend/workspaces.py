import hashlib
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.runner import BenchmarkRunner
from backend.auth_store import AuthStore
from backend.store import RunStore


class WorkspaceName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Enter a workspace name without control characters")
        return value


class InviteUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["github", "oidc", "local"]
    username: str = Field(min_length=1, max_length=128)


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "member"]


@dataclass
class WorkspaceRuntime:
    store: RunStore
    runner: BenchmarkRunner


class WorkspaceManager:
    def __init__(self, root_store, project_root: Path, data_dir: Path, secret_box, enabled=True):
        self.root_store = root_store
        self.project_root = project_root
        self.data_dir = data_dir
        self.secret_box = secret_box
        self.enabled = enabled
        self.runtimes = {}
        self.lock = threading.RLock()

    def initialize(self):
        with self.root_store._session() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('personal', 'team')),
                    schema_name TEXT NOT NULL UNIQUE,
                    personal_owner TEXT UNIQUE REFERENCES auth_users(id),
                    deleted_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workspace_members (
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    user_id TEXT NOT NULL REFERENCES auth_users(id),
                    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
                    PRIMARY KEY (workspace_id, user_id)
                )
            """)
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS workspace_one_owner ON workspace_members(workspace_id) WHERE role='owner'")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS workspace_invitations (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    target_user_id TEXT NOT NULL REFERENCES auth_users(id),
                    invited_by TEXT NOT NULL REFERENCES auth_users(id),
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'revoked')),
                    expires_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP + INTERVAL '7 days',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS workspace_invitation_target ON workspace_invitations(target_user_id, status)")
            schema = connection.execute("SELECT current_schema() AS name").fetchone()["name"]
            connection.execute("""
                INSERT INTO workspaces(id, name, kind, schema_name) VALUES ('legacy', '个人空间', 'personal', %s)
                ON CONFLICT(id) DO NOTHING
            """, (schema,))
            rows = connection.execute("SELECT id FROM workspaces WHERE deleted_at IS NULL").fetchall()
        for row in rows:
            runtime = self.runtime(row["id"])
            if row["id"] != "legacy":
                runtime.store.initialize()

    def _create_schema(self, connection, identifier):
        parent = connection.execute("SELECT current_schema() AS name").fetchone()["name"]
        prefix = hashlib.sha256(parent.encode()).hexdigest()[:12]
        schema = f"ws_{prefix}_{identifier}"
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
        RunStore.create_tables(connection)
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(parent)))
        return schema

    def ensure_personal(self, user):
        with self.root_store._session() as connection:
            connection.execute("SELECT id FROM auth_users WHERE id=%s FOR UPDATE", (user["id"],))
            if user["provider"] == "local":
                connection.execute("SELECT id FROM workspaces WHERE id='legacy' FOR UPDATE")
                connection.execute("DELETE FROM workspace_members WHERE workspace_id='legacy' AND user_id<>%s", (user["id"],))
                connection.execute("UPDATE workspaces SET personal_owner=%s WHERE id='legacy'", (user["id"],))
                identifier = "legacy"
            else:
                row = connection.execute("SELECT id FROM workspaces WHERE personal_owner=%s", (user["id"],)).fetchone()
                if row:
                    return row["id"]
                identifier = uuid.uuid4().hex
                schema = self._create_schema(connection, identifier)
                connection.execute("INSERT INTO workspaces(id, name, kind, schema_name, personal_owner) VALUES (%s, '个人空间', 'personal', %s, %s)",
                                   (identifier, schema, user["id"]))
            connection.execute("""
                INSERT INTO workspace_members VALUES (%s, %s, 'owner')
                ON CONFLICT(workspace_id, user_id) DO UPDATE SET role='owner'
            """, (identifier, user["id"]))
        return identifier

    def list_for_user(self, user):
        personal = self.ensure_personal(user)
        with self.root_store._session() as connection:
            rows = connection.execute("""
                SELECT w.id, w.name, w.kind, m.role FROM workspaces w
                JOIN workspace_members m ON m.workspace_id=w.id
                WHERE m.user_id=%s AND w.deleted_at IS NULL ORDER BY w.kind, w.created_at
            """, (user["id"],)).fetchall()
        return {"workspaces": [dict(row) for row in rows], "personal_workspace_id": personal}

    def require(self, connection, identifier, user, roles=None, team=False):
        row = connection.execute("""
            SELECT w.id, w.name, w.kind, m.role FROM workspaces w
            JOIN workspace_members m ON m.workspace_id=w.id
            WHERE w.id=%s AND m.user_id=%s AND w.deleted_at IS NULL
        """, (identifier, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Workspace not found")
        if (roles and row["role"] not in roles) or (team and row["kind"] != "team"):
            raise HTTPException(403, "This action requires a team owner or administrator")
        return dict(row)

    def access(self, request, user):
        personal = self.ensure_personal(user)
        identifier = request.headers.get("x-workspace-id")
        if request.url.path.endswith("/events"):
            query_identifier = request.query_params.get("workspace_id")
            if identifier and query_identifier and identifier != query_identifier:
                raise HTTPException(400, "Conflicting workspace IDs")
            identifier = identifier or query_identifier
        if request.url.path.startswith(("/api/auth/", "/api/workspaces")):
            identifier = personal
        identifier = identifier or personal
        with self.root_store._session() as connection:
            try:
                workspace = self.require(connection, identifier, user)
            except HTTPException as error:
                raise HTTPException(403, {"code": "workspace_unavailable", "message": "Workspace access has changed; select another workspace"}) from error
        path = request.url.path
        manage_config = request.method not in {"GET", "HEAD", "OPTIONS"} and (
            path.startswith(("/api/service-configs", "/api/provider-models", "/api/dify/names")) or path == "/api/system-settings"
            or (request.method == "DELETE" and path.startswith(("/api/plans/", "/api/runs/")))
        )
        if manage_config and workspace["role"] == "member":
            raise HTTPException(403, "Workspace configuration requires an owner or administrator")
        return self.runtime(identifier), workspace

    def runtime(self, identifier):
        with self.lock:
            if identifier in self.runtimes:
                return self.runtimes[identifier]
            if not self.enabled and identifier == "legacy":
                target_store = self.root_store
            else:
                with self.root_store._session() as connection:
                    row = connection.execute("SELECT schema_name FROM workspaces WHERE id=%s AND deleted_at IS NULL", (identifier,)).fetchone()
                if not row:
                    raise HTTPException(404, "Workspace not found")
                target_store = RunStore(self.root_store.database_url, initialize=False, schema_name=row["schema_name"])
            reports = self.data_dir / "reports" if identifier == "legacy" else self.data_dir / "workspaces" / identifier / "reports"
            runner = BenchmarkRunner(target_store, self.project_root, reports, self.secret_box, allow_environment_credentials=not self.enabled)
            runtime = WorkspaceRuntime(target_store, runner)
            self.runtimes[identifier] = runtime
            return runtime

    def scheduled_workspaces(self):
        if not self.enabled:
            return [(self.runtime("legacy"), {"id": "legacy", "role": "owner"})]
        with self.root_store._session() as connection:
            rows = connection.execute("SELECT id FROM workspaces WHERE deleted_at IS NULL").fetchall()
        return [(self.runtime(row["id"]), {"id": row["id"], "role": "owner"}) for row in rows]

    def still_member(self, identifier, user):
        with self.root_store._session() as connection:
            try:
                self.require(connection, identifier, user)
            except HTTPException:
                return False
        return True

    def shares_team(self, user_id, other_user_id):
        with self.root_store._session() as connection:
            return connection.execute("""
                SELECT 1 FROM workspace_members own
                JOIN workspace_members other ON own.workspace_id=other.workspace_id
                JOIN workspaces w ON w.id=own.workspace_id
                WHERE own.user_id=%s AND other.user_id=%s AND w.kind='team' AND w.deleted_at IS NULL
                LIMIT 1
            """, (user_id, other_user_id)).fetchone() is not None

    def _lock_team(self, connection, identifier, user, roles=("owner", "admin")):
        connection.execute("SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (identifier,))
        return self.require(connection, identifier, user, roles, team=True)

    def install(self, app):
        router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

        def user_from(request):
            user = getattr(request.state, "auth_user", None)
            if not self.enabled or not user:
                raise HTTPException(401, "Sign in to manage workspaces")
            return user

        @router.get("")
        def list_workspaces(request: Request):
            return self.list_for_user(user_from(request))

        @router.post("", status_code=201)
        def create_workspace(payload: WorkspaceName, request: Request):
            user = user_from(request)
            identifier = uuid.uuid4().hex
            with self.root_store._session() as connection:
                connection.execute("SELECT id FROM auth_users WHERE id=%s FOR UPDATE", (user["id"],))
                count = connection.execute("SELECT count(*) AS count FROM workspace_members m JOIN workspaces w ON w.id=m.workspace_id WHERE m.user_id=%s AND m.role='owner' AND w.kind='team' AND w.deleted_at IS NULL", (user["id"],)).fetchone()["count"]
                if count >= 20:
                    raise HTTPException(409, "You may own at most 20 teams")
                schema = self._create_schema(connection, identifier)
                connection.execute("INSERT INTO workspaces(id, name, kind, schema_name) VALUES (%s, %s, 'team', %s)", (identifier, payload.name, schema))
                connection.execute("INSERT INTO workspace_members VALUES (%s, %s, 'owner')", (identifier, user["id"]))
            return {"id": identifier, "name": payload.name, "kind": "team", "role": "owner"}

        @router.get("/invitations")
        def inbox(request: Request):
            user = user_from(request)
            with self.root_store._session() as connection:
                return connection.execute("""
                    SELECT i.id, i.workspace_id, w.name AS workspace_name, COALESCE(u.nickname, u.name) AS invited_by,
                           i.expires_at FROM workspace_invitations i
                    JOIN workspaces w ON w.id=i.workspace_id JOIN auth_users u ON u.id=i.invited_by
                    WHERE i.target_user_id=%s AND i.status='pending' AND i.expires_at>CURRENT_TIMESTAMP AND w.deleted_at IS NULL
                    ORDER BY i.created_at DESC
                """, (user["id"],)).fetchall()

        @router.post("/invitations/{invitation_id}/accept")
        def accept(invitation_id: str, request: Request):
            user = user_from(request)
            with self.root_store._session() as connection:
                invitation = connection.execute("SELECT workspace_id FROM workspace_invitations WHERE id=%s AND target_user_id=%s", (invitation_id, user["id"])).fetchone()
                if not invitation:
                    raise HTTPException(404, "Invitation not found")
                workspace = connection.execute("SELECT id FROM workspaces WHERE id=%s AND deleted_at IS NULL FOR UPDATE", (invitation["workspace_id"],)).fetchone()
                if not workspace:
                    raise HTTPException(404, "Workspace not found")
                accepted = connection.execute("UPDATE workspace_invitations SET status='accepted' WHERE id=%s AND status='pending' AND expires_at>CURRENT_TIMESTAMP RETURNING workspace_id", (invitation_id,)).fetchone()
                if not accepted:
                    raise HTTPException(409, "Invitation is expired or already processed")
                connection.execute("INSERT INTO workspace_members VALUES (%s, %s, 'member') ON CONFLICT DO NOTHING", (accepted["workspace_id"], user["id"]))
            return {"workspace_id": accepted["workspace_id"]}

        @router.post("/invitations/{invitation_id}/decline", status_code=204)
        def decline(invitation_id: str, request: Request):
            user = user_from(request)
            with self.root_store._session() as connection:
                row = connection.execute("UPDATE workspace_invitations SET status='declined' WHERE id=%s AND target_user_id=%s AND status='pending' RETURNING id", (invitation_id, user["id"])).fetchone()
                if not row:
                    raise HTTPException(404, "Invitation not found")

        @router.patch("/{identifier}")
        def rename(identifier: str, payload: WorkspaceName, request: Request):
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user_from(request))
                connection.execute("UPDATE workspaces SET name=%s WHERE id=%s", (payload.name, identifier))
            return {"name": payload.name}

        @router.get("/{identifier}/members")
        def members(identifier: str, request: Request):
            with self.root_store._session() as connection:
                self.require(connection, identifier, user_from(request))
                rows = connection.execute("SELECT u.id, COALESCE(u.nickname, u.name) AS name, u.avatar_version, u.username, u.provider, m.role FROM workspace_members m JOIN auth_users u ON u.id=m.user_id WHERE m.workspace_id=%s ORDER BY COALESCE(u.nickname, u.name), u.id", (identifier,)).fetchall()
                return [AuthStore.public_user(row) for row in rows]

        @router.post("/{identifier}/invitations", status_code=201)
        def invite(identifier: str, payload: InviteUser, request: Request):
            user = user_from(request)
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user)
                targets = connection.execute("SELECT id FROM auth_users WHERE provider=%s AND username=%s LIMIT 2", (payload.provider, payload.username.strip())).fetchall()
                if not targets:
                    raise HTTPException(404, "User not found; ask them to sign in to PrismLab first")
                if len(targets) != 1:
                    raise HTTPException(409, "Username is ambiguous; contact the platform administrator")
                target = targets[0]["id"]
                if connection.execute("SELECT 1 FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (identifier, target)).fetchone():
                    raise HTTPException(409, "User is already a member")
                if connection.execute("SELECT 1 FROM workspace_invitations WHERE workspace_id=%s AND target_user_id=%s AND status='pending' AND expires_at>CURRENT_TIMESTAMP", (identifier, target)).fetchone():
                    raise HTTPException(409, "A pending invitation already exists")
                invitation_id = uuid.uuid4().hex
                connection.execute("INSERT INTO workspace_invitations(id, workspace_id, target_user_id, invited_by) VALUES (%s, %s, %s, %s)", (invitation_id, identifier, target, user["id"]))
            return {"id": invitation_id}

        @router.get("/{identifier}/invitations")
        def sent_invitations(identifier: str, request: Request):
            with self.root_store._session() as connection:
                self.require(connection, identifier, user_from(request), {"owner", "admin"}, team=True)
                return connection.execute("SELECT i.id, u.username, u.provider, i.expires_at FROM workspace_invitations i JOIN auth_users u ON u.id=i.target_user_id WHERE i.workspace_id=%s AND i.status='pending' AND i.expires_at>CURRENT_TIMESTAMP ORDER BY i.created_at DESC", (identifier,)).fetchall()

        @router.delete("/{identifier}/invitations/{invitation_id}", status_code=204)
        def revoke(identifier: str, invitation_id: str, request: Request):
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user_from(request))
                if not connection.execute("UPDATE workspace_invitations SET status='revoked' WHERE id=%s AND workspace_id=%s AND status='pending' RETURNING id", (invitation_id, identifier)).fetchone():
                    raise HTTPException(404, "Invitation not found")

        @router.patch("/{identifier}/members/{user_id}")
        def change_role(identifier: str, user_id: str, payload: MemberRole, request: Request):
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user_from(request), {"owner"})
                row = connection.execute("UPDATE workspace_members SET role=%s WHERE workspace_id=%s AND user_id=%s AND role<>'owner' RETURNING user_id", (payload.role, identifier, user_id)).fetchone()
                if not row:
                    raise HTTPException(409, "Cannot change this member's role")
            return {"role": payload.role}

        @router.delete("/{identifier}/members/{user_id}", status_code=204)
        def remove_member(identifier: str, user_id: str, request: Request):
            with self.root_store._session() as connection:
                actor = self._lock_team(connection, identifier, user_from(request))
                target = connection.execute("SELECT role FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (identifier, user_id)).fetchone()
                if not target:
                    raise HTTPException(404, "Member not found")
                if target["role"] == "owner" or (actor["role"] == "admin" and target["role"] != "member"):
                    raise HTTPException(403, "Only the owner can manage administrators")
                connection.execute("DELETE FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (identifier, user_id))

        @router.post("/{identifier}/leave", status_code=204)
        def leave(identifier: str, request: Request):
            user = user_from(request)
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user, {"admin", "member"})
                connection.execute("DELETE FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (identifier, user["id"]))

        @router.delete("/{identifier}", status_code=204)
        def delete(identifier: str, request: Request):
            with self.root_store._session() as connection:
                self._lock_team(connection, identifier, user_from(request), {"owner"})
                target_store = self.runtime(identifier).store
                with target_store._session() as target:
                    active = target.execute("SELECT 1 FROM runs WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
                    generating = target.execute("SELECT 1 FROM run_ai_reports WHERE payload::jsonb->>'status'='generating' LIMIT 1").fetchone()
                if active or generating:
                    raise HTTPException(409, "Wait for active runs and AI reports to finish before deleting the team")
                connection.execute("UPDATE workspaces SET deleted_at=CURRENT_TIMESTAMP WHERE id=%s", (identifier,))

        app.include_router(router)
