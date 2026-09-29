"""Minimal .env loader for local development without extra dependencies."""

import locale
import os
from pathlib import Path


def load_local_env(filename=".env"):
    """Load KEY=VALUE pairs from a local .env file without overwriting real env vars."""
    env_path = Path(__file__).with_name(filename)
    if not env_path.is_file():
        return

    raw_bytes = env_path.read_bytes()
    for encoding in dict.fromkeys(("utf-8-sig", locale.getpreferredencoding(False), "gb18030")):
        try:
            content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UnicodeError(f"Cannot decode {env_path.name}; save it as UTF-8")

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
