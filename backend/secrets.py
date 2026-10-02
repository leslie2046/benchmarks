import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, key: bytes):
        self.fernet = Fernet(key)

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "SecretBox":
        configured = os.getenv("BENCHMARK_SECRET_KEY")
        if configured:
            return cls(configured.encode("ascii"))
        key_path = data_dir / "secret.key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
            try:
                key_path.chmod(0o600)
            except OSError:
                pass
        return cls(key_path.read_bytes().strip())

    def encrypt(self, value: str | None) -> str | None:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii") if value else None

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored API key cannot be decrypted with the current master key") from exc
