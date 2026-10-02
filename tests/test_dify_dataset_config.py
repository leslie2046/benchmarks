import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from backend import main
from backend.dify_names import fetch_names
from backend.runner import BenchmarkRunner
from backend.schemas import DifyNamesRequest, PlaygroundRequest, ServiceConfigCreate, TestPlanCreate
from backend.secrets import SecretBox
from backend.store import RunStore


class DifyDatasetConfigTests(unittest.TestCase):
    def test_direct_name_fetch_uses_the_configured_id_not_the_list(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'id': 'dataset-a', 'name': '产品知识库'}
        with patch('backend.dify_names.requests.get', return_value=response) as get:
            found = fetch_names('https://fixture/v1', 'dify-retrieve', 'secret', dataset_id='dataset-a')
        self.assertEqual(get.call_args.args[0], 'https://fixture/v1/datasets/dataset-a')
        self.assertIsNone(get.call_args.kwargs['params'])
        self.assertEqual(found['names'][0]['name'], '产品知识库')
        self.assertFalse(found['has_more'])

    def test_config_plan_playground_and_each_scenario_use_saved_dataset_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RunStore(root / 'db.sqlite3')
            box = SecretBox.from_data_dir(root)
            runner = BenchmarkRunner(store, Path(__file__).resolve().parents[1], root / 'reports', box)
            with patch.object(main, 'store', store), patch.object(main, 'secret_box', box), patch.object(main, 'check_models'):
                configs = []
                for dataset_id in ['dataset-a', 'dataset-b']:
                    configs.append(main.create_service_config(ServiceConfigCreate(name=dataset_id, provider='dify', dataset_id=dataset_id,
                        models=[{'name': None, 'benchmark': 'dify-retrieve', 'base_url': 'https://fixture'}], api_key='secret')))
                self.assertEqual(configs[0]['dataset_id'], 'dataset-a')
                payload = TestPlanCreate(name='Dify plan', benchmark='dify-retrieve', query='question', providers=[{'id': c['id']} for c in configs], concurrency_levels=[1])
                plan = main.create_plan(payload)
                self.assertIsNone(plan['dataset_id'])
                resolved = main._resolve_configs('dify-retrieve', plan['providers'])
                with patch('backend.runner.asyncio.create_task', side_effect=lambda coroutine: coroutine.close()):
                    run = runner.create_run(main._plan_request(plan), plan['id'], resolved)
                self.assertEqual([s['dataset_id'] for s in run['scenarios']], ['dataset-a', 'dataset-b'])
                for scenario in run['scenarios']:
                    cmd = runner.build_command(run, scenario, root / 'fixture.json')
                    self.assertEqual(cmd[cmd.index('--dataset-id') + 1], scenario['dataset_id'])
                # Snapshot is stable if the underlying configuration subsequently changes.
                changed = store.get_service_config(configs[0]['id'])
                changed['dataset_id'] = 'new-dataset'
                store.put_service_config(changed)
                self.assertEqual(run['scenarios'][0]['dataset_id'], 'dataset-a')
                request = PlaygroundRequest(benchmark='dify-retrieve', provider_id=configs[0]['id'], query='question')
                response = MagicMock(status_code=200, content=b'{}', encoding='utf-8')
                with patch('backend.playground.requests.post', return_value=response) as post:
                    main.playground(request)
                self.assertEqual(post.call_args.args[0], 'https://fixture/v1/datasets/new-dataset/retrieve')
                response = MagicMock(status_code=200)
                response.json.return_value = {'id': 'new-dataset', 'name': 'new name'}
                with patch('backend.dify_names.requests.get', return_value=response) as get:
                    main.dify_names(DifyNamesRequest(server_url='https://fixture', benchmark='dify-retrieve', config_id=configs[0]['id'], dataset_id='new-dataset'))
                self.assertEqual(get.call_args.args[0], 'https://fixture/v1/datasets/new-dataset')
                # Legacy plans continue to work, but new plans must bind a configured ID.
                changed['dataset_id'] = None
                store.put_service_config(changed)
                legacy = main._resolve_configs('dify-retrieve', [{'id': changed['id']}], 'legacy-id')[0]
                self.assertEqual(legacy['dataset_id'], 'legacy-id')
                with self.assertRaises(HTTPException):
                    main._resolve_configs('dify-retrieve', [{'id': changed['id']}])
                catalog = next(b for b in main.catalog()['benchmarks'] if b['id'] == 'dify-retrieve')
                self.assertFalse(next(p for p in catalog['providers'] if p['id'] == changed['id'])['endpoint_configured'])
                with self.assertRaises(HTTPException):
                    main.create_service_config(ServiceConfigCreate(name='missing ID', provider='dify', models=[{'name': None, 'benchmark': 'dify-retrieve', 'base_url': 'https://fixture'}]))
