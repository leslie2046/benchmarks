import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.dataset_routes import install_dataset_routes
from backend.dataset_store import DatasetStore
from backend.datasets import (DEFAULT_PROMPT, DatasetItem, GenerationOptions, build_dataset,
                              document_chunks, fetch_dify_chunks, generate_items, parse_import)
from backend.store import RunStore
from tests.database import create_test_store


class DatasetParsingTests(unittest.TestCase):
    def test_import_langfuse_and_ragas_and_roundtrip(self):
        values = [{'input': {'question': '问题'}, 'expected_output': {'answer': '答案'},
                   'metadata': {'source': '原文'}, 'reference_contexts': ['上下文'], 'id': 'ignored'}]
        for suffix, data in [('json', json.dumps({'items': values}, ensure_ascii=False)),
                             ('jsonl', json.dumps(values[0], ensure_ascii=False))]:
            item = parse_import('a.' + suffix, data.encode())[0]
            self.assertEqual(json.loads(item['input']), {'question': '问题'})
            self.assertEqual(item['additional_metadata']['_prismlab_legacy_values']['input'], {'question': '问题'})
            self.assertEqual(item['additional_metadata']['source'], '原文')
        csv = 'question,answer,reference_contexts,metadata\n问题,答案,"[""原文""]","{""source"":""file""}"\n'
        item = parse_import('test.csv', csv.encode('utf-8-sig'))[0]
        self.assertEqual(item['input'], '问题')
        self.assertEqual(item['context'], ['原文'])
        item = parse_import('ragas.json', b'[{"user_input":"q","reference":"a","reference_contexts":["c"]}]')[0]
        self.assertEqual(item['expected_output'], 'a')

    def test_invalid_rows_rejected_without_echoing_private_content(self):
        for suffix, data in [('json', b'[]'), ('json', b'[{}, {"input":"private"}]'),
                             ('json', b'[{"input":"q","metadata":[]}]'), ('json', b'[{"input":"q","reference_contexts":"bad"}]'),
                             ('csv', b'answer\na'), ('csv', b'input,metadata\nq,private'),
                             ('csv', b'input,answer\nq,a,unexpected'), ('jsonl', b'{broken')]:
            with self.subTest(suffix=suffix, data=data), self.assertRaises(ValueError):
                parse_import('data.' + suffix, data)
        for value in [None, '', '  ']:
            with self.assertRaises(ValueError):
                DatasetItem(input=value)
        with self.assertRaises(ValueError):
            DatasetItem(input=float('nan'))
        for value in [0, 501, 1.5, '2', True]:
            with self.assertRaises(ValidationError):
                GenerationOptions(size=value)

    def test_text_docx_pdf_and_limits(self):
        chunks = document_chunks('a.md', ('内容 ' * 2000).encode())
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item['content']) <= 4000 for item in chunks))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>PrismLab document</w:t></w:r></w:p></w:body></w:document>')
        self.assertIn('PrismLab document', document_chunks('a.docx', archive.getvalue())[0]['content'])
        from pypdf import PdfWriter
        pdf = PdfWriter(); pdf.add_blank_page(width=100, height=100); output = io.BytesIO(); pdf.write(output)
        for filename, data in [('scan.pdf', output.getvalue()), ('empty.txt', b' '), ('bad.exe', b'x'), ('big.txt', b'a' * 2000001)]:
            with self.assertRaises(ValueError):
                document_chunks(filename, data)

    def test_dify_pagination_provenance_filtering_and_redaction(self):
        config = {'id': 'config', 'base_url': 'https://dify.test/v1', 'dataset_id': 'dataset/id'}
        responses = [
            {'data': [{'id': 'doc1', 'name': '文档'}], 'has_more': True},
            {'data': [{'id': 's1', 'content': '知识内容'}, {'id': 's2', 'content': 'disabled', 'enabled': False}], 'has_more': True},
            {'data': [{'id': 's3', 'content': 'question', 'answer': 'answer'}]},
            {'data': [{'id': 'disabled', 'enabled': False}]},
        ]
        def response(*args, **kwargs):
            result = MagicMock(status_code=200); result.json.return_value = responses.pop(0); return result
        with patch('backend.datasets.requests.get', side_effect=response) as get:
            chunks = fetch_dify_chunks(config, 'private-key')
            self.assertEqual(len(chunks), 2)
            self.assertEqual(chunks[0]['metadata']['segment_id'], 's1')
            self.assertEqual(chunks[1]['content'], 'question\nanswer')
            self.assertIn('dataset%2Fid', get.call_args_list[0].args[0])
            self.assertEqual([call.kwargs['params']['page'] for call in get.call_args_list], [1, 1, 2, 2])
            self.assertTrue(all(call.kwargs['allow_redirects'] is False for call in get.call_args_list))
        with patch('backend.datasets.requests.get', return_value=MagicMock(status_code=401)):
            with self.assertRaises(ValueError) as error:
                fetch_dify_chunks(config, 'private-key')
            self.assertIn('401', str(error.exception)); self.assertNotIn('private-key', str(error.exception))



class DatasetApiTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.store = create_test_store(self, root)
        self.repo = DatasetStore(self.store)
        self.app = FastAPI()
        self.config = {'base_url': 'https://fixture.test', 'model': 'test-model', 'id': 'provider'}
        self.resolve = MagicMock(return_value=(self.config, 'private-key'))
        install_dataset_routes(self.app, self.store, self.resolve, lambda: self.store)
        self.client = TestClient(self.app)
        self.selection = {'id': 'provider', 'model': 'test-model'}

    def create(self):
        response = self.client.post('/api/datasets', json={'name': 'RAG 问答', 'description': 'test'})
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def generate(self, size=3):
        return self.client.post('/api/datasets/generate', data={'name': 'Generated', 'options': json.dumps({'size': size, 'llm': self.selection})}, files={'files': ('source.txt', b'Grounded source')})

    def test_settings_merge_reset_and_model_validation(self):
        self.store.save_system_settings({'default_llm': {'id': 'reports'}, 'unrelated': True})
        initial = self.client.get('/api/dataset-settings').json()
        self.assertEqual(initial['prompt'], DEFAULT_PROMPT)
        result = self.client.put('/api/dataset-settings', json={'default_llm': self.selection, 'prompt': 'Custom prompt'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['prompt'], 'Custom prompt')
        self.store.save_system_settings({'default_llm': None})
        self.assertEqual(self.client.get('/api/dataset-settings').json()['prompt'], 'Custom prompt')
        self.assertTrue(self.store.system_settings()['unrelated'])
        result = self.client.put('/api/dataset-settings', json={'default_llm': None, 'prompt': None})
        self.assertEqual(result.json()['prompt'], DEFAULT_PROMPT)
        self.assertIsNone(result.json()['default_llm'])
        with patch.object(self.resolve, 'side_effect', HTTPException(400, 'Invalid model')):
            self.assertEqual(self.client.put('/api/dataset-settings', json={'default_llm': self.selection}).status_code, 400)
        self.assertEqual(self.client.put('/api/dataset-settings', json={'prompt': '   '}).status_code, 422)

    def test_crud_search_pagination_export_and_import_roundtrip(self):
        identifier = self.create()
        path = '/api/datasets/' + identifier
        for index in range(12):
            self.assertEqual(self.client.post(path + '/items', json={'input': f'question {index}', 'expected_output': 'answer'}).status_code, 201)
        values = self.client.get(path + '/items?page=2&page_size=10').json()
        self.assertEqual(values['total'], 12); self.assertEqual(len(values['items']), 2)
        item = values['items'][0]
        self.assertEqual(self.client.put(path + '/items/' + item['id'], json={'input': {'q': 'edited'}, 'metadata': {'source': 'x'}, 'status': 'archived'}).status_code, 200)
        self.assertEqual(self.client.get(path + '/items?q=edited').json()['total'], 1)
        self.assertEqual(self.client.put(path, json={'name': 'Renamed', 'description': 'new'}).status_code, 200)
        self.assertEqual(self.client.get('/api/datasets?q=Renamed').json()['total'], 1)
        self.assertEqual(self.client.get('/api/datasets?q=missing').json()['total'], 0)
        export = self.client.get(path + '/export')
        response = self.client.post('/api/datasets/import', data={'name': 'Roundtrip'}, files={'file': ('dataset.json', export.content)})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['item_count'], 12)
        self.assertEqual(self.client.delete(path + '/items/' + item['id']).status_code, 204)
        self.assertEqual(self.repo.get(identifier)['item_count'], 11)
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(path + '/items').status_code, 404)

    def test_import_is_atomic_and_append_is_validated(self):
        response = self.client.post('/api/datasets/import', data={'name': 'Broken'}, files={'file': ('a.json', b'[{"input":"ok"},{}]')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.repo.page(1, 10, '')['total'], 0)
        identifier = self.create(); path = '/api/datasets/' + identifier
        self.assertEqual(self.client.post(path + '/import', files={'file': ('a.csv', b'input,expected_output\nq,a')}).status_code, 200)
        self.assertEqual(self.repo.get(identifier)['item_count'], 1)
        self.assertEqual(self.client.post(path + '/import', files={'file': ('bad.json', b'[]')}).status_code, 400)
        self.assertEqual(self.repo.get(identifier)['item_count'], 1)
        self.assertEqual(self.client.post('/api/datasets/import', data={'name': 'Too big'}, files={'file': ('a.json', b'a' * (10 * 1024 * 1024 + 1))}).status_code, 400)

    def test_generation_failure_resume_restart_and_edit_lock(self):
        with patch('backend.datasets.generate_items', side_effect=RuntimeError('private-key https://secret')):
            result = self.generate()
        self.assertEqual(result.status_code, 202)
        identifier = result.json()['id']; path = '/api/datasets/' + identifier
        failed = self.repo.get(identifier)
        self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('private-key', json.dumps(failed))
        def make(chunks, count, *args):
            return [DatasetItem(input=f'q{i}', expected_output='a', reference_contexts=[chunks[0]['content']]).model_dump() for i in range(count)]
        with patch('backend.datasets.generate_items', side_effect=make):
            self.assertEqual(self.client.post(path + '/retry').status_code, 202)
        ready = self.repo.get(identifier)
        self.assertEqual(ready['status'], 'ready'); self.assertEqual(ready['item_count'], 3)
        self.assertEqual(self.client.post(path + '/retry').status_code, 409)
        self.repo.mutate(identifier, lambda c, d: d.update(status='generating'))
        self.assertEqual(self.client.post(path + '/items', json={'input': 'q'}).status_code, 409)
        self.assertEqual(self.client.delete(path).status_code, 409)
        self.assertEqual(self.client.post(path + '/retry').status_code, 409)
        reopened = DatasetStore(RunStore(self.store.database_url))
        self.assertEqual(reopened.get(identifier)['status'], 'failed')
        self.assertEqual(reopened.get(identifier)['item_count'], 3)

    def test_partial_output_is_preserved_and_never_reported_as_complete(self):
        dataset = self.repo.create({'name': 'Partial', 'description': '', 'status': 'generating', 'source_type': 'documents', 'target_size': 6})
        chunks = [{'id': 'source', 'content': 'text', 'metadata': {}}]
        first = [DatasetItem(input='one', expected_output='answer').model_dump()]
        with patch('backend.datasets.generate_items', side_effect=[first] + [[]] * 5):
            build_dataset(self.repo, dataset['id'], chunks, None, self.config, 'key', DEFAULT_PROMPT)
        saved = self.repo.get(dataset['id'])
        self.assertEqual(saved['status'], 'failed'); self.assertEqual(saved['item_count'], 1)
        self.assertEqual(self.repo.items(dataset['id'])['total'], 1)

    def test_missing_source_and_model_do_not_create_datasets(self):
        self.assertEqual(self.client.post('/api/datasets/generate', data={'name': 'x', 'options': '{"size":1}'}, files={'files': ('a.txt', b'text')}).status_code, 400)
        self.assertEqual(self.client.post('/api/datasets/generate', data={'name': 'x', 'options': json.dumps({'llm': self.selection})}).status_code, 400)
        self.assertEqual(self.repo.page(1, 10, '')['total'], 0)

    def test_workspace_schema_isolation(self):
        second = create_test_store(self, Path(tempfile.mkdtemp()))
        identifier = self.create()
        other = DatasetStore(second)
        self.assertEqual(other.page(1, 10, '')['total'], 0)
        with self.assertRaises(HTTPException) as error:
            other.get(identifier)
        self.assertEqual(error.exception.status_code, 404)
        second.save_system_settings({'dataset_prompt': 'Other workspace prompt'})
        self.assertEqual(self.client.get('/api/dataset-settings').json()['prompt'], DEFAULT_PROMPT)

class LegacyDatasetModelTests(unittest.TestCase):
    def test_legacy_catalog_credential_resolves_and_remains_selectable(self):
        store = MagicMock()
        model = {'name': 'legacy-model', 'alias': 'Alias', 'benchmark': 'llm', 'base_url': 'https://fixture/v1/chat/completions'}
        config = {'id': 'p', 'models': [model], 'model': 'legacy-model', 'credential_id': None}
        store.get_service_config.return_value = config
        store.system_settings.return_value = {}
        resolve = MagicMock(return_value=(config, 'key'))
        app = FastAPI()
        install_dataset_routes(app, store, resolve, lambda: store)
        response = TestClient(app).put('/api/dataset-settings', json={'default_llm': {'id': 'p', 'model': 'Alias', 'credential_id': 'legacy'}})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(resolve.call_args.args[0].credential_id)
        settings = store.save_system_settings.call_args.args[0]
        self.assertEqual(settings['dataset_default_llm'], {'id': 'p', 'model': 'Alias', 'credential_id': 'legacy'})


if __name__ == '__main__':
    unittest.main()
