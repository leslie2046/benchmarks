import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi import HTTPException
from pydantic import ValidationError
from backend import main
from backend.dify_names import fetch_names
from backend.schemas import DifyNamesRequest
from backend.secrets import SecretBox
from backend.store import RunStore


class DifyNameTests(unittest.TestCase):
    def response(self, body, status=200):
        response = MagicMock(status_code=status)
        response.json.return_value = body
        return response

    def test_application_info_name_and_normalized_api_path(self):
        for url in ['https://fixture', 'https://fixture/v1/', 'https://fixture/proxy/v1']:
            with patch('backend.dify_names.requests.get', return_value=self.response({'name': '应用名称', 'secret': 'not returned'})) as get:
                found = fetch_names(url, 'dify-chat', 'secret')
                self.assertEqual(found['names'], [{'id': 'app', 'name': '应用名称'}])
                self.assertNotIn('secret', str(found))
                self.assertFalse(get.call_args.kwargs['allow_redirects'])
                self.assertTrue(get.call_args.args[0].endswith('/v1/info'))
                self.assertNotIn('/v1/v1/', get.call_args.args[0])

    def test_datasets_pagination_empty_and_invalid_records(self):
        body = {'data': [{'id': 'a', 'name': '知识库 A'}, {'id': 'b', 'name': '知识库 B'}, {'id': 'bad'}, None], 'has_more': True}
        with patch('backend.dify_names.requests.get', return_value=self.response(body)) as get:
            found = fetch_names('https://fixture/v1', 'dify-retrieve', 'secret', 2)
            self.assertEqual(len(found['names']), 2)
            self.assertEqual(found['page'], 2)
            self.assertTrue(found['has_more'])
            self.assertEqual(get.call_args.kwargs['params'], {'page': 2, 'limit': 100})
        with patch('backend.dify_names.requests.get', return_value=self.response({'data': []})):
            self.assertEqual(fetch_names('https://fixture', 'dify-retrieve', 'secret')['names'], [])

    def test_failures_are_actionable_without_leaking_keys(self):
        for status in [401, 403, 307, 404, 500]:
            with patch('backend.dify_names.requests.get', return_value=self.response({}, status)):
                with self.assertRaises(ValueError) as raised:
                    fetch_names('https://fixture', 'dify-chat', 'sensitive-key')
                self.assertNotIn('sensitive-key', str(raised.exception))
        for body in [[], {'name': ''}, {'name': 5}]:
            with patch('backend.dify_names.requests.get', return_value=self.response(body)), self.assertRaises(ValueError):
                fetch_names('https://fixture', 'dify-chat', 'secret')
        with patch('backend.dify_names.requests.get', side_effect=requests.Timeout('secret')), self.assertRaises(ValueError):
            fetch_names('https://fixture', 'dify-chat', 'secret')
        invalid = self.response({})
        invalid.json.side_effect = ValueError('bad JSON')
        with patch('backend.dify_names.requests.get', return_value=invalid), self.assertRaises(ValueError):
            fetch_names('https://fixture', 'dify-chat', 'secret')
        with patch('backend.dify_names.requests.get') as get, self.assertRaises(ValueError):
            fetch_names('https://fixture', 'dify-chat', None)
        get.assert_not_called()

    def test_saved_key_is_reused_read_only_and_cannot_be_sent_to_new_host_or_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RunStore(root / 'db.sqlite3')
            secret_box = SecretBox.from_data_dir(root)
            saved = {'id': 'fixture', 'provider': 'dify', 'name': 'old', 'benchmark': 'dify-chat',
                     'base_url': 'https://fixture', 'api_key_encrypted': secret_box.encrypt('saved-key'),
                     'created_at': '2026-10-02T00:00:00Z', 'updated_at': '2026-10-02T00:00:00Z'}
            store.put_service_config(saved)
            with patch.object(main, 'store', store), patch.object(main, 'secret_box', secret_box), \
                    patch('backend.dify_names.requests.get', return_value=self.response({'name': 'Fetched app'})) as get:
                found = main.dify_names(DifyNamesRequest(server_url='https://fixture/v1', benchmark='dify-chat', config_id='fixture'))
                self.assertEqual(found['names'][0]['name'], 'Fetched app')
                self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer saved-key')
                self.assertEqual(store.get_service_config('fixture'), saved)
                get.reset_mock()
                for url, benchmark in [('https://other', 'dify-chat'), ('https://fixture', 'dify-retrieve')]:
                    with self.assertRaises(HTTPException) as raised:
                        main.dify_names(DifyNamesRequest(server_url=url, benchmark=benchmark, config_id='fixture'))
                    self.assertEqual(raised.exception.status_code, 400)
                get.assert_not_called()
                main.dify_names(DifyNamesRequest(server_url='https://other', benchmark='dify-chat', config_id='fixture', api_key='new-key'))
                self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer new-key')

    def test_schema_rejects_other_providers_benchmarks_and_invalid_pages(self):
        for overrides in [{'provider': 'vllm'}, {'benchmark': 'llm'}, {'page': 0}]:
            payload = {'server_url': 'https://fixture', 'benchmark': 'dify-chat', **overrides}
            with self.assertRaises(ValidationError):
                DifyNamesRequest(**payload)
