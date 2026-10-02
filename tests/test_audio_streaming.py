import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.providers import AUDIO_PROVIDERS
from backend.catalog import allowed_provider_ids
from shared.llm_stream import iter_chat
from backend.playground import stream_playground
from backend.schemas import PlaygroundRequest
from backend import main


class AudioStreamingTests(unittest.TestCase):
    def response(self, lines):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_lines.return_value = lines
        return response

    def test_audio_provider_and_credentials(self):
        self.assertEqual(allowed_provider_ids('audio'), {'xinference', 'siliconflow', 'vllm'})
        for provider, key in [('siliconflow', 'SILICONFLOW_API_KEY'), ('vllm', 'VLLM_API_KEY')]:
            self.assertEqual(main._credential_env('audio', provider), key)
            self.assertEqual(AUDIO_PROVIDERS[provider]['api_key_env'], key)

    def test_audio_cli_uses_provider_defaults_and_explicit_overrides(self):
        from cli import perf_audio
        with patch('sys.argv', ['perf_audio.py', '--provider', 'siliconflow']), patch.dict('os.environ', {}, clear=True):
            args = perf_audio.parse_args()
            self.assertEqual(args.model, 'FunAudioLLM/SenseVoiceSmall')
            self.assertEqual(args.base_url, 'https://api.siliconflow.cn/v1/audio/transcriptions')
        with patch('sys.argv', ['perf_audio.py', '--provider', 'vllm', '--model=m', '--base-url=http://fixture/transcriptions']):
            args = perf_audio.parse_args()
            self.assertEqual(args.model, 'm')
            self.assertEqual(args.base_url, 'http://fixture/transcriptions')

    def test_delta_is_yielded_before_upstream_completion_and_close_cleans_up(self):
        def lines():
            yield 'data: {"choices":[{"delta":{"content":"第一段"}}]}'
            raise AssertionError('Must not read future content before yielding')
        response = self.response(lines())
        with patch('shared.llm_stream.requests.post', return_value=response):
            stream = iter_chat('http://fixture', 'm', None, 'q', capture=True)
            self.assertEqual(next(stream)['content'], '第一段')
            stream.close()
        response.__exit__.assert_called_once()

    def test_ndjson_result_and_safe_error(self):
        payload = PlaygroundRequest(benchmark='llm', provider_id='fixture', query='q')
        config = {'base_url': 'http://fixture', 'model': 'm'}
        response = self.response([
            'data: {"choices":[{"delta":{"content":"你好"},"finish_reason":"stop"}],"usage":{"completion_tokens":2}}',
            'data: [DONE]',
        ])
        with patch('shared.llm_stream.requests.post', return_value=response):
            events = [json.loads(line) for line in stream_playground(payload, config, 'secret')]
        self.assertEqual([item['type'] for item in events], ['delta', 'result'])
        self.assertEqual(events[-1]['result']['data']['content'], '你好')
        self.assertGreaterEqual(events[-1]['result']['data']['ttft_ms'], 0)
        with patch('shared.llm_stream.requests.post', return_value=self.response(['data: invalid'])):
            lines = list(stream_playground(payload, config, 'secret'))
        self.assertEqual(json.loads(lines[0])['type'], 'error')
        self.assertNotIn('secret', lines[0])

    def test_audio_models_can_be_configured_for_both_providers(self):
        from backend.store import RunStore
        from backend.secrets import SecretBox
        from backend.schemas import ServiceConfigCreate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(main, 'store', RunStore(root / 'db.sqlite3')), patch.object(main, 'secret_box', SecretBox.from_data_dir(root)):
                for provider in ['siliconflow', 'vllm']:
                    config = main.create_service_config(ServiceConfigCreate(name=provider, provider=provider, models=[{
                        'name': 'asr-fixture', 'benchmark': 'audio', 'credentials': [{'name': 'Default', 'server_url': 'http://fixture:9999'}]
                    }]))
                    resolved, key = main._playground_access(PlaygroundRequest(benchmark='audio', provider_id=config['id'], audio_base64='YQ=='))
                    self.assertTrue(resolved['base_url'].endswith('/v1/audio/transcriptions'))
