import hashlib
import secrets
import uuid

from backend.store import RunStore


class AuthStore:
    def __init__(self, store: RunStore):
        self.store = store

    def initialize(self):
        with self.store._session() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    username TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (provider, subject)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    auth_version TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS nickname TEXT")
            connection.execute("ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS avatar BYTEA")
            connection.execute("ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS avatar_version TEXT")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS auth_flows (
                    state_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    binding_hash TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions (expires_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions (user_id)")

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def create_session(self, provider: str, subject: str, username: str, name: str, version: str) -> tuple[str, dict]:
        token = secrets.token_urlsafe(32)
        with self.store._session() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE expires_at <= CURRENT_TIMESTAMP")
            user = connection.execute("""
                INSERT INTO auth_users (id, provider, subject, username, name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider, subject) DO UPDATE SET
                    username = EXCLUDED.username, name = EXCLUDED.name, updated_at = CURRENT_TIMESTAMP
                RETURNING id, provider, username, COALESCE(nickname, name) AS name, avatar_version
            """, (uuid.uuid4().hex, provider, subject, username[:128], name[:256])).fetchone()
            connection.execute("""
                DELETE FROM auth_sessions WHERE user_id = %s AND token_hash NOT IN (
                    SELECT token_hash FROM auth_sessions WHERE user_id = %s
                    ORDER BY created_at DESC LIMIT 9
                )
            """, (user["id"], user["id"]))
            connection.execute("""
                INSERT INTO auth_sessions (token_hash, user_id, auth_version, expires_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '24 hours')
            """, (self.digest(token), user["id"], version))
        return token, self.public_user(user)

    @staticmethod
    def public_user(row):
        user = dict(row)
        version = user.pop("avatar_version", None)
        user["nickname"] = user["name"]
        user["avatar_url"] = f"/api/auth/profile/avatar/{user['id']}/{version}" if version else None
        return user

    def update_nickname(self, user_id, nickname):
        with self.store._session() as connection:
            row = connection.execute("""
                UPDATE auth_users SET nickname=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s
                RETURNING id, provider, username, COALESCE(nickname, name) AS name, avatar_version
            """, (nickname, user_id)).fetchone()
        return self.public_user(row)

    def update_avatar(self, user_id, avatar):
        version = hashlib.sha256(avatar).hexdigest() if avatar else None
        with self.store._session() as connection:
            row = connection.execute("""
                UPDATE auth_users SET avatar=%s, avatar_version=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s
                RETURNING id, provider, username, COALESCE(nickname, name) AS name, avatar_version
            """, (avatar, version, user_id)).fetchone()
        return self.public_user(row)

    def avatar(self, user_id, version):
        with self.store._session() as connection:
            row = connection.execute("SELECT avatar FROM auth_users WHERE id=%s AND avatar_version=%s", (user_id, version)).fetchone()
        return bytes(row["avatar"]) if row and row["avatar"] else None

    def user(self, token: str, version: str) -> dict | None:
        if not token or len(token) > 128:
            return None
        with self.store._session() as connection:
            row = connection.execute("""
                SELECT auth_users.id, provider, username, COALESCE(nickname, name) AS name, avatar_version FROM auth_users
                JOIN auth_sessions ON auth_users.id = auth_sessions.user_id
                WHERE token_hash = %s AND auth_version = %s AND expires_at > CURRENT_TIMESTAMP
            """, (self.digest(token), version)).fetchone()
        return self.public_user(row) if row else None

    def revoke(self, token: str):
        with self.store._session() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (self.digest(token),))

    def save_flow(self, state: str, provider: str, binding: str):
        with self.store._session() as connection:
            connection.execute("DELETE FROM auth_flows WHERE expires_at <= CURRENT_TIMESTAMP")
            connection.execute("""
                INSERT INTO auth_flows (state_hash, provider, binding_hash, expires_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
            """, (self.digest(state), provider, self.digest(binding)))

    def consume_flow(self, state: str, provider: str, binding: str) -> bool:
        if not state or not binding or len(state) > 256:
            return False
        with self.store._session() as connection:
            row = connection.execute("""
                DELETE FROM auth_flows WHERE state_hash = %s AND provider = %s
                    AND binding_hash = %s AND expires_at > CURRENT_TIMESTAMP
                RETURNING state_hash
            """, (self.digest(state), provider, self.digest(binding))).fetchone()
        return row is not None
