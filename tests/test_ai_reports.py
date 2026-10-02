import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from backend import main
from backend.ai_reports import performance_summary, generate_report
from backend.schemas import AiReportRequest, ServiceConfigCreate, SystemSettingsUpdate
from backend.secrets import SecretBox
from backend.store import RunStore, utc_now
from shared.llm_stream import stream_chat


class AiReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = RunStore(root / 'test.sqlite3')
        self.box = SecretBox.from_data_dir(root)
        for name, value in [('store', self.store), ('secret_box', self.box)]:
            mocked = patch.object(main, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        with patch.object(main, 'check_models'):
            self.config = main.create_service_config(ServiceConfigCreate(name='Mock provider', provider='vllm', models=[
                {'name': 'llm-fixture', 'alias': 'Report model', 'benchmark': 'llm',
                 'credentials': [{'name': 'Default', 'server_url': 'https://fixture.example', 'api_key': 'secret-key'}]},
                {'name': 'embedding-fixture', 'benchmark': 'embedding', 'base_url': 'https://fixture.example'}]))
        self.selection = {'id': self.config['id'], 'model': 'Report model'}
        now = utc_now()
        self.run = {'id': 'run1', 'name': 'Test run', 'benchmark': 'llm', 'status': 'completed',
                    'created_at': now, 'updated_at': now, 'query': 'private query', 'api_key': 'secret-key',
                    'scenarios': [{'status': 'completed', 'provider_name': 'Mock', 'model': 'tested-llm', 'concurrency': 1,
                                   'base_url': 'https://secret.example', 'error': 'secret-key',
                                   'result': {'success_count': 10, 'qps_success': 2, 'metrics': {
                                       'latency_ms': {'p95': 400, 'secret': 'private'},
                                       'ttft_ms': {'avg': 100}, 'secret': {'avg': 'private'}}}}]}
        self.store.create(self.run)

    def configure(self):
        return main.update_system_settings(SystemSettingsUpdate(default_llm=self.selection))

    def start(self, regenerate=False):
        tasks = BackgroundTasks()
        report = main.create_ai_report('run1', AiReportRequest(regenerate=regenerate), tasks)
        return report, tasks

    def test_settings_select_only_existing_llm_and_persist_without_inference(self):
        with patch('backend.ai_reports.stream_chat') as inference:
            self.assertIsNone(main.system_settings()['default_llm'])
            result = self.configure()
            inference.assert_not_called()
        self.assertEqual(result['default_llm']['model'], 'Report model')
        self.assertTrue(result['default_llm']['credential_id'])
        self.assertNotIn('secret-key', json.dumps(result))
        self.assertEqual(RunStore(self.store.path).system_settings(), result)
        with self.assertRaises(HTTPException):
            main.update_system_settings(SystemSettingsUpdate(default_llm={'id': self.config['id'], 'model': 'embedding-fixture'}))
        with self.assertRaises(HTTPException):
            main.update_system_settings(SystemSettingsUpdate(default_llm={'id': self.config['id'], 'model': 'Report model', 'credential_id': 'missing'}))
        self.assertIsNone(main.update_system_settings(SystemSettingsUpdate())['default_llm'])

    def test_manual_generation_persists_and_read_or_repeat_does_not_call_model(self):
        self.configure()
        self.assertEqual(main.get_ai_report('run1')['status'], 'none')
        report, tasks = self.start()
        self.assertEqual(report['status'], 'generating')
        with self.assertRaises(HTTPException) as duplicate:
            self.start()
        self.assertEqual(duplicate.exception.status_code, 409)
        with patch('backend.ai_reports.generate_report', return_value='A saved report') as generate:
            asyncio.run(tasks())
            generated = main.get_ai_report('run1')
            self.assertEqual(generated['content'], 'A saved report')
            self.assertEqual(generated['status'], 'ready')
            self.assertEqual(generate.call_args.args[2], 'secret-key')
            self.assertEqual(generate.call_args.args[1]['model'], 'llm-fixture')
            self.assertEqual(self.start()[0]['content'], 'A saved report')
            generate.assert_called_once()
        reopened = RunStore(self.store.path)
        self.assertEqual(reopened.ai_report('run1'), generated)
        self.assertEqual(reopened.get('run1'), self.run)

    def test_regeneration_failure_keeps_previous_and_success_replaces(self):
        self.configure()
        _, tasks = self.start()
        with patch('backend.ai_reports.generate_report', return_value='original'):
            asyncio.run(tasks())
        _, tasks = self.start(True)
        with patch('backend.ai_reports.generate_report', side_effect=ValueError('secret-key https://secret')):
            asyncio.run(tasks())
        failed = main.get_ai_report('run1')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['content'], 'original')
        self.assertNotIn('secret-key', json.dumps(failed))
        _, tasks = self.start(True)
        with patch('backend.ai_reports.generate_report', return_value='updated'):
            asyncio.run(tasks())
        self.assertEqual(main.get_ai_report('run1')['content'], 'updated')

    def test_restart_recovers_and_deletion_does_not_recreate_report(self):
        self.configure()
        report, _ = self.start()
        reopened = RunStore(self.store.path)
        self.assertEqual(reopened.ai_report('run1')['status'], 'failed')
        self.store.delete_run('run1')
        self.store.finish_ai_report('run1', report['generation_id'], 'orphan')
        self.assertEqual(self.store.ai_report('run1')['status'], 'none')
        with self.assertRaises(HTTPException):
            main.get_ai_report('run1')

    def test_report_requires_terminal_run_and_configured_default(self):
        with self.assertRaises(HTTPException) as missing:
            self.start()
        self.assertEqual(missing.exception.status_code, 400)
        self.configure()
        self.run['status'] = 'running'
        self.store.save(self.run)
        with self.assertRaises(HTTPException) as active:
            self.start()
        self.assertEqual(active.exception.status_code, 409)

    def test_summary_excludes_credentials_inputs_urls_and_invalid_numbers(self):
        self.run['scenarios'][0]['result']['metrics']['latency_ms']['avg'] = float('nan')
        summary = performance_summary(self.run)
        encoded = json.dumps(summary, allow_nan=False)
        for forbidden in ['secret-key', 'private query', 'https://', 'NaN', 'private']:
            self.assertNotIn(forbidden, encoded)
        with patch('backend.ai_reports.stream_chat', return_value=({}, 'Report')) as stream:
            self.assertEqual(generate_report(self.run, {'base_url': 'https://fixture', 'model': 'llm'}, 'key', 'zh-CN'), 'Report')
        self.assertIn('400', stream.call_args.args[3])
        self.assertFalse(stream.call_args.kwargs['capture_reasoning'])
        with patch('backend.ai_reports.stream_chat', return_value=({}, '  ')):
            with self.assertRaises(ValueError):
                generate_report(self.run, {'base_url': 'fixture', 'model': 'llm'}, None, 'en')

    def test_http_settings_and_report_flow(self):
        client = TestClient(main.app)
        self.assertEqual(client.get('/api/system-settings').json()['default_llm'], None)
        self.assertEqual(client.put('/api/system-settings', json={'default_llm': self.selection}).status_code, 200)
        with patch('backend.ai_reports.generate_report', return_value='HTTP report') as generate:
            response = client.post('/api/runs/run1/ai-report', json={})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(client.get('/api/runs/run1/ai-report').json()['content'], 'HTTP report')
            generate.assert_called_once()
        self.assertEqual(client.get('/api/runs/missing/ai-report').status_code, 404)

    def test_report_does_not_capture_reasoning_or_accept_truncated_output(self):
        response = MagicMock()
        response.__enter__.return_value = response
        def lines(reason):
            return ['data: ' + json.dumps({'choices': [{'delta': {'reasoning_content': 'private reasoning'}}]}),
                    'data: ' + json.dumps({'choices': [{'delta': {'content': 'Report body'}}]}),
                    'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': reason}]}), 'data: [DONE]']
        response.iter_lines.return_value = lines('stop')
        with patch('shared.llm_stream.requests.post', return_value=response):
            _, content = stream_chat('https://fixture', 'model', None, 'prompt', capture=True, capture_reasoning=False, require_complete=True)
            self.assertEqual(content, 'Report body')
            response.iter_lines.return_value = lines('length')
            with self.assertRaises(ValueError):
                stream_chat('https://fixture', 'model', None, 'prompt', capture=True, require_complete=True)


if __name__ == '__main__':
    unittest.main()
