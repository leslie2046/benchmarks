import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.providers import LLM_PROVIDERS
from backend import main
from backend.catalog import allowed_provider_ids
from backend.connectivity import ConnectivityError, check_models
from backend.endpoints import endpoint_url, server_root
from backend.model_discovery import list_models, verify_key, ModelDiscoveryError
from backend.schemas import PlaygroundRequest, ProviderAccess, ServiceConfigCreate, SystemSettingsUpdate
from backend.secrets import SecretBox
from backend.store import RunStore


class DeepSeekTests(unittest.TestCase):
    def response(self, status=200):
        response = MagicMock(status_code=status)
        response.json.return_value = {'data': [{'id': 'deepseek-flash'}, {'id': 'deepseek-v4-pro'}]}
        return response

    def test_provider_only_supports_llm_and_endpoints_accept_root_v1_or_full(self):
        self.assertIn('deepseek', allowed_provider_ids('llm'))
        for benchmark in ['embedding', 'reranker', 'audio']:
            self.assertNotIn('deepseek', allowed_provider_ids(benchmark))
        self.assertEqual(LLM_PROVIDERS['deepseek']['api_key_env'], 'DEEPSEEK_API_KEY')
        for url in ['https://api.deepseek.com', 'https://api.deepseek.com/v1', 'https://api.deepseek.com/chat/completions', 'https://api.deepseek.com/v1/chat/completions']:
            actual = endpoint_url(url, 'llm', 'deepseek')
            self.assertEqual(actual.count('/chat/completions'), 1)
            self.assertEqual(endpoint_url(actual, 'llm', 'deepseek'), actual)
        self.assertEqual(server_root('https://api.deepseek.com/chat/completions'), 'https://api.deepseek.com')

    def test_discovery_classifies_models_and_verification_is_read_only(self):
        with patch('backend.model_discovery.requests.get', return_value=self.response()) as get:
            models = list_models('deepseek', 'https://api.deepseek.com', 'secret')
            verify_key('deepseek', 'https://api.deepseek.com/v1', 'secret')
        self.assertTrue(all(item['benchmark'] == 'llm' for item in models))
        self.assertEqual(get.call_args_list[0].args[0], 'https://api.deepseek.com/models')
        self.assertEqual(get.call_args_list[1].args[0], 'https://api.deepseek.com/v1/models')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        with patch('backend.model_discovery.requests.get', return_value=self.response(401)):
            with self.assertRaises(ModelDiscoveryError):
                verify_key('deepseek', 'https://api.deepseek.com', 'bad-key')

    def test_model_validation_checks_available_ids_without_paid_inference(self):
        model = {'provider': 'deepseek', 'benchmark': 'llm', 'base_url': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-flash'}
        with patch('backend.model_discovery.requests.get', return_value=self.response()), patch('backend.connectivity.requests.post') as post:
            check_models([model], 'secret')
            model['model'] = 'unknown'
            with self.assertRaises(ConnectivityError):
                check_models([model], 'secret')
            post.assert_not_called()

    def test_saved_credentials_are_reused_by_playground_and_default_analysis_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RunStore(root / 'runs.sqlite3')
            box = SecretBox.from_data_dir(root)
            with patch.object(main, 'store', store), patch.object(main, 'secret_box', box):
                config = main.create_service_config(ServiceConfigCreate(name='DeepSeek', provider='deepseek', models=[{
                    'name': 'deepseek-flash', 'benchmark': 'llm', 'credentials': [{'name': 'Default', 'server_url': 'https://api.deepseek.com', 'api_key': 'secret'}]}]))
                self.assertNotIn('secret', str(config))
                access, key = main._playground_access(PlaygroundRequest(benchmark='llm', provider_id=config['id'], model='deepseek-flash', query='test'))
                self.assertEqual(access['base_url'], 'https://api.deepseek.com/chat/completions')
                self.assertEqual(key, 'secret')
                main.update_system_settings(SystemSettingsUpdate(default_llm={'id': config['id'], 'model': 'deepseek-flash'}))
                with patch('backend.model_discovery.requests.get', return_value=self.response()):
                    result = main.verify_provider_access(ProviderAccess(provider='deepseek', server_url='https://api.deepseek.com', config_id=config['id'], credential_id=config['models'][0]['credentials'][0]['id']))
                self.assertTrue(result['valid'])


if __name__ == '__main__':
    unittest.main()
