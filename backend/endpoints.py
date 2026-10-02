"""Translate server roots into benchmark endpoints, retaining legacy URLs."""

from urllib.parse import urlsplit, urlunsplit


def endpoint_url(server_url: str, benchmark: str, provider: str) -> str:
    if benchmark.startswith("dify-"):
        return server_url.rstrip("/")
    path = {
        "llm": "/chat/completions" if provider == "deepseek" else "/v1/chat/completions",
        "embedding": "/v1/embeddings",
        "reranker": "/v1/reranks" if provider == "aliyun" else "/v2/rerank" if provider == "xunfei" else "/v1/rerank",
        "audio": "/v1/audio/transcriptions",
    }[benchmark]
    parts = urlsplit(server_url.rstrip("/"))
    current = parts.path.rstrip("/")
    if current.endswith(path):
        return server_url.rstrip("/")
    if provider == "xunfei" and benchmark == "reranker" and current.endswith(("/v1", "/v2")):
        path = "/rerank"
    if current.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    return urlunsplit((parts.scheme, parts.netloc, current + path, parts.query, parts.fragment))


def server_root(url: str) -> str:
    parts = urlsplit(url.rstrip("/"))
    path = parts.path
    if path.endswith(("/v1/rerank", "/v2/rerank")):
        path = path[:-len("/rerank")]
    for suffix in ("/v1/embeddings", "/v1/reranks", "/v1/audio/transcriptions", "/v1/chat/completions", "/chat/completions"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")
