import hashlib
import re
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import requests

from backend.endpoints import server_root


BALANCE_PROVIDERS = {"deepseek", "moonshot", "siliconflow"}
_cache = OrderedDict()
_cache_lock = threading.Lock()


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Invalid balance amount")
    amount = Decimal(str(value))
    if not amount.is_finite() or len(str(value)) > 100 or abs(amount) > Decimal("1e30") or amount.as_tuple().exponent < -18:
        raise ValueError("Invalid balance amount")
    return format(amount, "f")


def _fetch(provider, server_url, api_key):
    parts = urlsplit(server_root(server_url))
    path = parts.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    route = {"deepseek": "/user/balance", "moonshot": "/v1/users/me/balance", "siliconflow": "/v1/user/info"}[provider]
    url = urlunsplit((parts.scheme, parts.netloc, path + route, "", ""))
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=(3, 6), allow_redirects=False)
        if response.status_code in {401, 403}:
            return {"status": "invalid_key", "balances": []}
        if response.status_code == 410:
            return {"status": "unsupported", "balances": []}
        if not 200 <= response.status_code < 300:
            return {"status": "error", "balances": []}
        body = response.json()
        if not isinstance(body, dict) or body.get("status") is False:
            raise ValueError("Invalid balance response")
        if provider == "deepseek":
            rows = body.get("balance_infos")
            if not isinstance(rows, list) or not rows:
                raise ValueError("Missing balance")
            balances = []
            for row in rows:
                currency = row.get("currency") if isinstance(row, dict) else None
                if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                    raise ValueError("Invalid currency")
                balances.append({"currency": currency, "amount": _amount(row.get("total_balance"))})
        else:
            data = body.get("data")
            if not isinstance(data, dict):
                raise ValueError("Missing balance")
            if provider == "moonshot":
                if body.get("code") != 0:
                    raise ValueError("Balance request rejected")
                currency = "CNY" if parts.hostname == "api.moonshot.cn" else None
                amount = data.get("available_balance")
            else:
                if body.get("code") != 20000:
                    raise ValueError("Balance request rejected")
                currency = "CNY" if parts.hostname == "api.siliconflow.cn" else None
                amount = data.get("totalBalance")
            balances = [{"currency": currency, "amount": _amount(amount)}]
        return {"status": "available", "balances": balances}
    except (requests.RequestException, ValueError, InvalidOperation, OverflowError):
        return {"status": "error", "balances": []}


def get_balance(workspace_id, config_id, credential_id, provider, server_url, api_key):
    if not api_key:
        return {"status": "unconfigured", "balances": []}
    if provider not in BALANCE_PROVIDERS:
        return {"status": "unsupported", "balances": []}
    fingerprint = hashlib.sha256(f"{server_url}\0{api_key}".encode()).hexdigest()
    cache_key = (workspace_id, config_id, credential_id, provider, fingerprint)
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return deepcopy(cached[1])
    result = _fetch(provider, server_url, api_key)
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    ttl = 60 if result["status"] in {"available", "unsupported"} else 15
    with _cache_lock:
        _cache[cache_key] = (time.monotonic() + ttl, deepcopy(result))
        _cache.move_to_end(cache_key)
        while len(_cache) > 256:
            _cache.popitem(last=False)
    return result
