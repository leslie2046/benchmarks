from urllib.parse import urlparse


PLACEHOLDER_TOKENS = ("your-", "replace-with", "<", ">", "{", "}")


def is_placeholder_url(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.lower()
    if any(token in lowered for token in PLACEHOLDER_TOKENS):
        return True
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        return True
    return parsed.scheme not in {"http", "https"} or not parsed.hostname
