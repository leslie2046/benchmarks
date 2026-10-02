import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from backend.schemas import PlaygroundRequest
from backend.playground import run_playground, stream_playground
from shared.llm_stream import stream_chat


class SystemPromptTests(unittest.TestCase):
    def test_real_wire_messages_and_empty_compatibility(self):
        for prompt in (None, "", "  ", "Answer in Chinese."):
            with self.subTest(prompt=prompt):
                response = MagicMock()
                response.__enter__.return_value = response
                response.iter_lines.return_value = [
                    'data: ' + json.dumps({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}),
                    'data: [DONE]',
                ]
                with patch("shared.llm_stream.requests.post", return_value=response) as post:
                    stream_chat("https://fixture.test/chat", "fixture", None, "question", system_prompt=prompt)
                expected = [{"role": "user", "content": "question"}]
                if prompt and prompt.strip():
                    expected.insert(0, {"role": "system", "content": prompt})
                self.assertEqual(post.call_args.kwargs["json"]["messages"], expected)

    def test_both_playground_paths_forward_prompt(self):
        request = PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q", system_prompt="Be concise.")
        config = {"base_url": "https://fixture.test/chat", "model": "fixture"}
        resolved = ({}, {})
        with patch("backend.llm_parameters.resolve_parameters", return_value=resolved), patch(
            "shared.llm_stream.stream_chat", return_value=({"latency_ms": 1, "ttft_ms": 1}, "ok")
        ) as chat:
            run_playground(request, config, None)
        self.assertEqual(chat.call_args.kwargs["system_prompt"], "Be concise.")
        with patch("shared.llm_stream.iter_chat", return_value=iter([])) as chat:
            list(stream_playground(request, config, None, resolved))
        self.assertEqual(chat.call_args.kwargs["system_prompt"], "Be concise.")

    def test_validation_and_old_requests(self):
        self.assertIsNone(PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q").system_prompt)
        with self.assertRaises(ValidationError):
            PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q", system_prompt="x" * 20_001)
        with self.assertRaises(ValidationError):
            PlaygroundRequest(benchmark="embedding", provider_id="fixture", text="q", system_prompt="rule")

    def test_playground_omits_unset_output_limit_on_wire(self):
        from backend.llm_parameters import resolve_parameters
        config = {"provider": "vllm", "model": "fixture", "base_url": "https://fixture.test/chat"}
        for limit in (None, 4096):
            request = PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q", max_tokens=limit)
            wire, snapshot = resolve_parameters(config, {}, request.max_tokens)
            self.assertEqual(wire, {} if limit is None else {"max_tokens": limit})
            response = MagicMock()
            response.__enter__.return_value = response
            response.iter_lines.return_value = ['data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}', 'data: [DONE]']
            with patch("shared.llm_stream.requests.post", return_value=response) as post:
                list(stream_playground(request, config, None, (wire, snapshot)))
            payload = post.call_args.kwargs["json"]
            if limit is None:
                self.assertNotIn("max_tokens", payload)
                self.assertNotIn("max_tokens", snapshot["service_defaults"])
            else:
                self.assertEqual(payload["max_tokens"], limit)
