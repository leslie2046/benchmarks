import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

from backend import main, provider_balances
from backend.provider_balances import get_balance
from backend.secrets import SecretBox


def response(body, status=200):
    result = MagicMock(status_code=status)
    result.json.return_value = body
    return result


class ProviderBalanceTests(unittest.TestCase):
    def setUp(self):
        provider_balances._cache.clear()

    def fetch(self, provider="deepseek", key="fixture-key", space="space", url="https://cloud.test/v1/chat/completions", credential="cred"):
        return get_balance(space, "config", credential, provider, url, key)

    def test_deepseek_preserves_currencies_and_zero_or_negative_balances(self):
        body = {"is_available": False, "balance_infos": [{"currency": "CNY", "total_balance": "0.00"}, {"currency": "USD", "total_balance": "-0.125"}]}
        with patch("backend.provider_balances.requests.get", return_value=response(body)) as get:
            result = self.fetch()
        self.assertEqual(result["balances"], [{"currency": "CNY", "amount": "0.00"}, {"currency": "USD", "amount": "-0.125"}])
        self.assertEqual(result["status"], "available")
        self.assertEqual(get.call_args.args[0], "https://cloud.test/user/balance")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer fixture-key"})
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(get.call_args.kwargs["timeout"], (3, 6))

    def test_moonshot_and_siliconflow_use_total_available_not_cash_only(self):
        for provider, body, field, host in (
            ("moonshot", {"code": 0, "data": {"available_balance": 12.5, "cash_balance": 1}}, "/v1/users/me/balance", "https://api.moonshot.cn"),
            ("siliconflow", {"code": 20000, "data": {"totalBalance": "12.50", "balance": "1"}}, "/v1/user/info", "https://api.siliconflow.cn"),
        ):
            with patch("backend.provider_balances.requests.get", return_value=response(body)) as get:
                result = self.fetch(provider, url=host + "/v1")
                self.assertEqual(get.call_args.args[0], host + field)
                self.assertEqual(result["status"], "available")
                self.assertEqual(result["balances"][0]["currency"], "CNY")
                self.assertIn(result["balances"][0]["amount"], ("12.5", "12.50"))

    def test_custom_gateway_currency_is_not_guessed(self):
        with patch("backend.provider_balances.requests.get", return_value=response({"code": 0, "data": {"available_balance": 3}})) as get:
            result = self.fetch("moonshot", url="https://gateway.test/proxy/v1")
        self.assertEqual(get.call_args.args[0], "https://gateway.test/proxy/v1/users/me/balance")
        self.assertIsNone(result["balances"][0]["currency"])

    def test_unconfigured_and_unsupported_do_not_contact_upstream(self):
        with patch("backend.provider_balances.requests.get") as get:
            self.assertEqual(self.fetch(key=None)["status"], "unconfigured")
            for provider in ("qwen", "minimax", "volcengine", "vllm", "xinference", "aliyun", "xunfei", "huaweiyun"):
                self.assertEqual(self.fetch(provider)["status"], "unsupported")
            get.assert_not_called()

    def test_invalid_key_http_failure_and_redirect_do_not_become_zero(self):
        for status in (401, 403, 302, 404, 429, 500):
            self.setUp()
            with patch("backend.provider_balances.requests.get", return_value=response({}, status)):
                result = self.fetch()
            self.assertEqual(result["status"], "invalid_key" if status in {401, 403} else "error")
            self.assertEqual(result["balances"], [])

    def test_retired_balance_endpoint_is_explicitly_unsupported(self):
        with patch("backend.provider_balances.requests.get", return_value=response({"code": 20092}, 410)):
            self.assertEqual(self.fetch("siliconflow")["status"], "unsupported")

    def test_malformed_and_nonfinite_values_are_rejected(self):
        for body in ([], {}, {"balance_infos": []}, {"balance_infos": [{"currency": "not money", "total_balance": "1"}]}, *({"balance_infos": [{"currency": "CNY", "total_balance": amount}]} for amount in (None, True, "NaN", "Infinity", "1e-999999", "1e999999"))):
            self.setUp()
            with patch("backend.provider_balances.requests.get", return_value=response(body)):
                self.assertEqual(self.fetch()["status"], "error")
        upstream = response({})
        upstream.json.side_effect = ValueError("fixture-key")
        with patch("backend.provider_balances.requests.get", return_value=upstream):
            self.assertNotIn("fixture-key", str(self.fetch()))

    def test_timeout_is_safe(self):
        with patch("backend.provider_balances.requests.get", side_effect=requests.Timeout("fixture-key")):
            result = self.fetch()
        self.assertEqual(result["status"], "error")
        self.assertNotIn("fixture-key", str(result))

    def test_cache_is_scoped_by_workspace_key_url_and_credential(self):
        body = {"balance_infos": [{"currency": "CNY", "total_balance": "2"}]}
        with patch("backend.provider_balances.requests.get", return_value=response(body)) as get:
            self.fetch()
            self.fetch()
            self.assertEqual(get.call_count, 1)
            self.fetch(space="other-space")
            self.fetch(key="new-key")
            self.fetch(url="https://other.test")
            self.fetch(credential="other-credential")
            self.assertEqual(get.call_count, 5)
        self.assertNotIn("fixture-key", str(provider_balances._cache))

    def test_cache_expires_and_is_bounded(self):
        body = {"balance_infos": [{"currency": "CNY", "total_balance": "2"}]}
        with patch("backend.provider_balances.requests.get", return_value=response(body)) as get, patch("backend.provider_balances.time.monotonic", return_value=0):
            self.fetch()
        with patch("backend.provider_balances.requests.get", return_value=response(body)) as get, patch("backend.provider_balances.time.monotonic", return_value=61):
            self.fetch()
            get.assert_called_once()
            for index in range(260):
                self.fetch(credential=str(index))
        self.assertLessEqual(len(provider_balances._cache), 256)

    def test_endpoint_only_uses_saved_workspace_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            box = SecretBox.from_data_dir(Path(directory))
            config = {"id": "config", "provider": "deepseek", "models": [{"name": "m", "benchmark": "llm", "credentials": [{"id": "cred", "name": "Default", "server_url": "https://saved.test", "api_key_encrypted": box.encrypt("fixture-key")}]}]}
            store = MagicMock()
            store.get_service_config.return_value = config
            with patch.object(main, "store", store), patch.object(main, "secret_box", box), patch("backend.provider_balances.requests.get", return_value=response({"balance_infos": [{"currency": "CNY", "total_balance": "1"}]})) as get:
                client = TestClient(main.app)
                result = client.get("/api/service-configs/config/balance?credential_id=cred&server_url=https://untrusted.test")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers["cache-control"], "no-store")
                self.assertEqual(get.call_args.args[0], "https://saved.test/user/balance")
                self.assertNotIn("fixture-key", result.text)
                self.assertEqual(client.get("/api/service-configs/config/balance?credential_id=foreign").status_code, 404)
                store.get_service_config.return_value = None
                self.assertEqual(client.get("/api/service-configs/foreign/balance?credential_id=cred").status_code, 404)
                get.assert_called_once()
