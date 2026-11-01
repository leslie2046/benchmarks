import io
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from backend.auth import AuthConfig, AuthService, SESSION_COOKIE
from backend.auth_store import AuthStore
from backend.profile import MAX_AVATAR_BYTES
from backend.secrets import SecretBox
from backend.workspaces import WorkspaceManager
from tests.database import create_test_store


class ProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = create_test_store(self, self.directory)
        self.storage = AuthStore(self.root)
        self.storage.initialize()
        self.service = AuthService(AuthConfig(mode="app", password="fixture-password", public_url="http://testserver"), self.storage,
                                   "profile-fixture-signing-secret-at-least-32-characters")
        self.app = FastAPI()
        self.service.install(self.app)
        self.owner, self.owner_user = self.client("github", "owner", "original-owner")
        self.other, self.other_user = self.client("oidc", "other", "other")

    def client(self, provider, subject, name):
        token, user = self.storage.create_session(provider, subject, subject, name, self.service.version)
        client = TestClient(self.app)
        self.addCleanup(client.close)
        client.cookies.set(SESSION_COOKIE, token)
        client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": self.service.csrf(token)})
        return client, user

    def image(self, format="PNG", size=(400, 300)):
        output = io.BytesIO()
        image = Image.new("RGB", size, "blue")
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "metadata-must-be-removed")
        image.save(output, format=format, **({"pnginfo": metadata} if format == "PNG" else {}))
        return output.getvalue()

    def upload(self, client=None, data=None, content_type="image/png"):
        return (client or self.owner).put("/api/auth/profile/avatar", content=self.image() if data is None else data,
                                          headers={"Content-Type": content_type})

    def test_nickname_is_persistent_and_cannot_change_identity_or_other_users(self):
        updated = self.owner.patch("/api/auth/profile", json={"nickname": "  新昵称 👩‍💻  "})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "新昵称 👩‍💻")
        self.assertEqual(updated.json()["nickname"], "新昵称 👩‍💻")
        self.assertEqual(updated.json()["username"], "owner")
        self.assertEqual(updated.json()["id"], self.owner_user["id"])
        self.assertNotIn("subject", updated.json())
        self.assertEqual(self.other.get("/api/auth/session").json()["user"]["name"], "other")
        for provider in ("github", "oidc", "local"):
            client, user = self.client(provider, "persistent", "provider-name")
            self.assertEqual(client.patch("/api/auth/profile", json={"nickname": "Saved nickname"}).status_code, 200)
            token, again = self.storage.create_session(provider, "persistent", "new-username", "changed-provider-name", self.service.version)
            self.assertEqual(again["name"], "Saved nickname")
            self.assertEqual(again["id"], user["id"])
            self.assertEqual(self.storage.user(token, self.service.version)["name"], "Saved nickname")

    def test_nickname_validation_and_mass_assignment(self):
        for nickname in ("", "   ", "bad\nname", "bad\x00name", "x" * 81, None, 23):
            with self.subTest(nickname=nickname):
                self.assertEqual(self.owner.patch("/api/auth/profile", json={"nickname": nickname}).status_code, 422)
        for field in ("id", "user_id", "provider", "username", "role", "avatar_url"):
            self.assertEqual(self.owner.patch("/api/auth/profile", json={"nickname": "Name", field: "other"}).status_code, 422)
        self.assertEqual(self.owner.get("/api/auth/session").json()["user"]["name"], "original-owner")

    def test_avatar_normalization_versioning_removal_and_login_persistence(self):
        for format, content_type in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
            with self.subTest(format=format):
                result = self.upload(data=self.image(format), content_type=content_type)
                self.assertEqual(result.status_code, 200, result.text)
                url = result.json()["avatar_url"]
                image_response = self.owner.get(url)
                self.assertEqual(image_response.status_code, 200)
                self.assertEqual(image_response.headers["content-type"], "image/png")
                self.assertEqual(image_response.headers["x-content-type-options"], "nosniff")
                with Image.open(io.BytesIO(image_response.content)) as image:
                    self.assertEqual(image.size, (256, 256))
                    self.assertNotIn("private", image.info)
                    self.assertFalse(image.getexif())
        token, user = self.storage.create_session("github", "owner", "renamed-owner", "provider-name", self.service.version)
        self.assertEqual(user["avatar_url"], url)
        self.assertEqual(self.storage.user(token, self.service.version)["avatar_url"], url)
        self.assertEqual(self.owner.delete("/api/auth/profile/avatar").json()["avatar_url"], None)
        self.assertEqual(self.owner.get(url).status_code, 404)
        self.assertIsNone(self.owner.get("/api/auth/session").json()["user"]["avatar_url"])

    def test_avatar_rejects_unsafe_corrupt_empty_oversize_and_high_resolution_images(self):
        cases = (
            (b"<svg onload='alert(1)'/>", "image/svg+xml", 415),
            (b"<svg onload='alert(1)'/>", "image/png", 422),
            (b"not-an-image", "image/png", 422),
            (self.image()[:35], "image/png", 422),
            (b"", "image/png", 413),
            (b"x" * (MAX_AVATAR_BYTES + 1), "image/png", 413),
            (self.image(size=(2500, 2000)), "image/png", 422),
            (self.image(size=(4097, 1)), "image/png", 422),
        )
        for data, content_type, status in cases:
            with self.subTest(size=len(data), content_type=content_type):
                self.assertEqual(self.upload(data=data, content_type=content_type).status_code, status)
        self.assertIsNone(self.owner.get("/api/auth/session").json()["user"]["avatar_url"])

    def test_profile_requires_authentication_csrf_and_trusted_origin(self):
        guest = TestClient(self.app)
        self.addCleanup(guest.close)
        self.assertEqual(guest.patch("/api/auth/profile", json={"nickname": "Name"}).status_code, 401)
        self.assertEqual(self.upload(client=guest).status_code, 401)
        self.assertEqual(guest.delete("/api/auth/profile/avatar").status_code, 401)
        self.assertEqual(self.owner.patch("/api/auth/profile", json={"nickname": "Name"}, headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        self.assertEqual(self.owner.put("/api/auth/profile/avatar", content=self.image(), headers={"Content-Type": "image/png", "Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.owner.delete("/api/auth/profile/avatar", headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        url = self.upload().json()["avatar_url"]
        self.assertEqual(guest.get(url).status_code, 401)
        self.assertEqual(self.other.get(url).status_code, 404)

    def test_existing_user_migration_is_idempotent_and_preserves_original_names(self):
        with self.root._session() as connection:
            connection.execute("ALTER TABLE auth_users DROP COLUMN nickname, DROP COLUMN avatar, DROP COLUMN avatar_version")
        self.storage.initialize()
        self.storage.initialize()
        user = self.owner.get("/api/auth/session").json()["user"]
        self.assertEqual(user["id"], self.owner_user["id"])
        self.assertEqual(user["nickname"], "original-owner")
        self.assertIsNone(user["avatar_url"])

    def test_avatars_and_member_nicknames_require_shared_active_team(self):
        manager = WorkspaceManager(self.root, Path(__file__).resolve().parents[1], self.directory, SecretBox.from_data_dir(self.directory))
        manager.initialize()
        self.service.workspaces = manager
        manager.install(self.app)

        def cleanup_schemas():
            from psycopg import sql
            with self.root._session() as connection:
                for row in connection.execute("SELECT schema_name FROM workspaces WHERE id<>'legacy'").fetchall():
                    connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(row["schema_name"])))

        self.addCleanup(cleanup_schemas)
        self.owner.get("/api/auth/session")
        self.other.get("/api/auth/session")
        self.owner.patch("/api/auth/profile", json={"nickname": "Team nickname"})
        url = self.upload().json()["avatar_url"]
        team = self.owner.post("/api/workspaces", json={"name": "Avatar team"}).json()["id"]
        invitation = self.owner.post(f"/api/workspaces/{team}/invitations", json={"provider": "oidc", "username": "other"}).json()["id"]
        self.assertEqual(self.other.get(url).status_code, 404)
        self.assertEqual(self.other.post(f"/api/workspaces/invitations/{invitation}/accept").status_code, 200)
        self.assertEqual(self.other.get(url).status_code, 200)
        members = self.other.get(f"/api/workspaces/{team}/members").json()
        profile = next(member for member in members if member["id"] == self.owner_user["id"])
        self.assertEqual(profile["name"], "Team nickname")
        self.assertEqual(profile["avatar_url"], url)
        self.assertEqual(self.owner.delete(f"/api/workspaces/{team}/members/{self.other_user['id']}").status_code, 204)
        self.assertEqual(self.other.get(url).status_code, 404)
