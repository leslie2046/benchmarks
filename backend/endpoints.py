"""Translate server roots into benchmark endpoints, retaining legacy URLs."""

from urllib.parse import urlsplit, urlunsplit


def endpoint_url(server_url: str, benchmark: str, provider: str) -> str:
    if benchmark.startswith("dify-"):
        return server_url.rstrip("/")
    path = {
        "llm": "/chat/completions" if provider == "deepseek" else "/v1/chat/completions",
        "embedding": "/v2/embeddings" if provider == "xunfei" else "/v1/embeddings",
        "reranker": "/v1/reranks" if provider == "aliyun" else "/v2/rerank" if provider == "xunfei" else "/v1/rerank",
        "audio": "/v1/audio/transcriptions",
    }[benchmark]
    parts = urlsplit(server_url.rstrip("/"))
    current = parts.path.rstrip("/")
    # Model Studio has different compatibility prefixes for chat and Qwen rerank.
    # Normalize only an explicit compatibility segment; retain custom roots/hosts.
    if provider == "aliyun" and benchmark in {"llm", "embedding", "reranker"}:
        segments = current.split("/")
        prefix = "compatible-api" if benchmark == "reranker" else "compatible-mode"
        segments = [prefix if segment in {"compatible-api", "compatible-mode"} else segment for segment in segments]
        current = "/".join(segments)
    if current.endswith(path):
        return urlunsplit((parts.scheme, parts.netloc, current, parts.query, parts.fragment))
    if provider == "xunfei" and benchmark in {"reranker", "embedding"}:
        suffix = "/rerank" if benchmark == "reranker" else "/embeddings"
        if current.endswith(("/v1" + suffix, "/v2" + suffix)):
            return urlunsplit((parts.scheme, parts.netloc, current, parts.query, parts.fragment))
        if current.endswith(("/v1", "/v2")):
            path = suffix
    if current.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    return urlunsplit((parts.scheme, parts.netloc, current + path, parts.query, parts.fragment))


def server_root(url: str) -> str:
    parts = urlsplit(url.rstrip("/"))
    path = parts.path
    if path.endswith(("/v1/rerank", "/v2/rerank", "/v2/embeddings")):
        path = path[:path.rfind("/")]
    for suffix in ("/v1/embeddings", "/v1/reranks", "/v1/audio/transcriptions", "/v1/chat/completions", "/chat/completions"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")
