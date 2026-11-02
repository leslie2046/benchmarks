"""Real DeepEval pipelines with deterministic LLM responses; no paid/cloud calls."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.dataset_golden import Golden, canonical_item, golden_dict
from backend.datasets import DEFAULT_PROMPT, DatasetItem, GenerationOptions, generate_items, parse_import
from backend.deepeval_generation import WorkspaceLLM
from tests import test_datasets as dataset_fixtures


class SDKFixture:
    def __init__(self, score=0.9):
        self.score = score
        self.calls = []
        self.serial = 0

    def __call__(self, endpoint, model, key, prompt, **kwargs):
        self.calls.append((model, prompt))
        self.serial += 1
        schema = json.loads(prompt.split('No Markdown.\n')[-1])
        properties = schema['properties']
        if 'data' in properties:
            value = {'data': [{'input': 'fixture one'}, {'input': 'fixture two'}]}
        elif 'score' in properties:
            value = {'score': self.score, 'feedback': 'Add detail'}
        elif 'rewritten_input' in properties:
            value = {'rewritten_input': f'improved {self.serial}'}
        elif 'scenario' in properties:
            value = {'scenario': 'Support', 'task': 'Answer product questions', 'input_format': 'A question'}
        elif 'input' in properties:
            value = {'input': f'styled question {self.serial}'}
        else:
            value = {'response': f'grounded response {self.serial}'}
        return {'output_tokens': 11}, json.dumps(value)


class GoldenSchemaTests(unittest.TestCase):
    def golden(self):
        return Golden(input='How?', expected_output='Do this', actual_output='Done',
                      context=['reference'], retrieval_context=['retrieved'],
                      additional_metadata={'custom': [1, '值']}, comments='Review',
                      tools_called=[{'name': 'search', 'input_parameters': {'q': 'how'}, 'output': {'hits': []}}],
                      expected_tools=[{'name': 'search'}], source_file='source.md', name='A case',
                      expected_labels={'intent': 'help'}, expectations={'must': ['Cite a source'], 'must_not': ['Invent']},
                      custom_column_key_values={'team': 'RAG'}, token_cost=0.12, input_token_count=12, output_token_count=30)

    def test_full_sdk_schema_roundtrip_and_aliases(self):
        golden = self.golden()
        expected = golden.model_dump(mode='json')
        for values in (expected, golden.model_dump(mode='json', by_alias=True)):
            record = parse_import('sdk.json', json.dumps([values]).encode())[0]
            self.assertEqual(golden_dict(record), expected)
            self.assertEqual(Golden.model_validate(golden_dict(record)).model_dump(mode='json'), expected)
        from deepeval.dataset import EvaluationDataset
        dataset = EvaluationDataset(goldens=[Golden.model_validate(golden_dict(record))])
        self.assertEqual(len(dataset.goldens), 1)

    def test_native_synthesizer_exports_import_directly(self):
        from pathlib import Path
        from deepeval.synthesizer import Synthesizer
        synth = Synthesizer(model=WorkspaceLLM(DeepEvalPipelineTests.config, 'unused'))
        synth.synthetic_goldens = [self.golden()]
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('json', 'jsonl', 'csv'):
                path = synth.save_as(suffix, directory, file_name='native', quiet=True)
                row = parse_import('native.' + suffix, Path(path).read_bytes())[0]
                self.assertEqual(row['input'], self.golden().input)
                self.assertEqual(row['expected_output'], self.golden().expected_output)
                self.assertEqual(row['context'], ['reference'])

    def test_legacy_read_is_lossless_idempotent_and_does_not_mutate_payload(self):
        old = {'id': 'app-id', 'dataset_id': 'dataset', 'input': {'q': ['one']}, 'expected_output': ['a'],
               'reference_contexts': ['ctx'], 'metadata': {'_prismlab_legacy_values': 'existing'}, 'status': 'archived'}
        original = json.dumps(old)
        item = canonical_item(old)
        self.assertEqual(item, canonical_item(item))
        self.assertEqual(json.dumps(old), original)
        self.assertEqual(item['id'], 'app-id')
        self.assertEqual(item['status'], 'archived')
        self.assertEqual(item['context'], ['ctx'])
        metadata = item['additional_metadata']
        self.assertEqual(metadata['_prismlab_legacy_values'], 'existing')
        self.assertEqual(metadata['_prismlab_legacy_values_'], {'input': {'q': ['one']}, 'expected_output': ['a']})
        self.assertNotIn('status', golden_dict(item))
        self.assertNotIn('id', golden_dict(item))

    def test_conflicts_unknown_fields_and_invalid_sdk_fields_are_rejected(self):
        for value in ({'input': 'q', 'context': ['a'], 'reference_contexts': ['b']},
                      {'input': 'q', 'unknown_field': 'must not disappear'},
                      {'input': 'q', 'expected_tools': [{'wrong': 'tool'}]},
                      {'input': 'q', 'images_mapping': {'secret': {'url': '/etc/passwd'}}},
                      {'input': 'q', 'expectations': {'must': ['  ']}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_import('a.json', json.dumps([value]).encode())
        for text in ('true', '123', 'null'):
            self.assertEqual(parse_import('a.csv', f'input\n{text}'.encode())[0]['input'], text)


class DeepEvalPipelineTests(unittest.TestCase):
    config = {'base_url': 'https://local-model/v1/chat/completions', 'model': 'workspace-model'}
    chunks = [{'id': 'a', 'content': 'Product context A', 'metadata': {'filename': 'a.md'}},
              {'id': 'b', 'content': 'Product context B', 'metadata': {'filename': 'b.md'}}]

    def test_real_sdk_context_filtration_evolution_style_and_expected_output(self):
        fixture = SDKFixture()
        usage = {'requests': 0, 'output_tokens': 0}
        with patch('backend.deepeval_generation.stream_chat', side_effect=fixture) as stream:
            items = generate_items(self.chunks, 2, self.config, 'local-secret', DEFAULT_PROMPT, [],
                                   GenerationOptions(size=2, max_concurrent=1).model_dump(),
                                   ({**self.config, 'model': 'critic-model'}, 'critic-secret'), usage)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['context'], ['Product context A', 'Product context B'])
        self.assertTrue(items[0]['expected_output'].startswith('grounded response'))
        metadata = items[0]['additional_metadata']
        self.assertEqual(metadata['synthetic_input_quality'], 0.9)
        self.assertEqual(len(metadata['evolutions']), 1)
        self.assertFalse(metadata['prismlab_generation']['review_required'])
        self.assertEqual(metadata['prismlab_generation']['sources'][1]['filename'], 'b.md')
        self.assertIn('critic-model', [model for model, _ in fixture.calls])
        self.assertEqual(usage['requests'], len(fixture.calls))
        self.assertEqual(usage['output_tokens'], len(fixture.calls) * 11)
        self.assertTrue(all(c.kwargs['require_complete'] and not c.kwargs['capture_reasoning'] for c in stream.call_args_list))
        self.assertEqual(os.environ['DEEPEVAL_TELEMETRY_OPT_OUT'], '1')

    def test_real_sdk_low_scores_are_preserved_and_flagged(self):
        fixture = SDKFixture(score=0.1)
        with patch('backend.deepeval_generation.stream_chat', side_effect=fixture):
            items = generate_items(self.chunks, 2, self.config, 'key', DEFAULT_PROMPT, [],
                                   GenerationOptions(size=2, num_evolutions=0, max_quality_retries=2,
                                                     include_expected_output=False).model_dump())
        self.assertEqual(len(items), 2)
        self.assertIsNone(items[0]['expected_output'])
        metadata = items[0]['additional_metadata']
        self.assertTrue(metadata['prismlab_generation']['review_required'])
        self.assertEqual(metadata['synthetic_input_quality'], 0.1)
        self.assertEqual(metadata['evolutions'], [])
        self.assertEqual(sum('"score"' in prompt.split('No Markdown.\n')[-1] for _, prompt in fixture.calls), 4)

    def test_real_sdk_seed_and_scratch_methods(self):
        for context in (['ground truth'], None):
            fixture = SDKFixture()
            chunks = [{'id': 'seed', 'golden': {'input': 'Example seed?', 'context': context}, 'metadata': {}}]
            with patch('backend.deepeval_generation.stream_chat', side_effect=fixture):
                items = generate_items(chunks, 2, self.config, 'key', DEFAULT_PROMPT, [],
                                       GenerationOptions(method='goldens', seed_dataset_id='d', num_evolutions=0).model_dump())
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]['context'], context)
            if context is None:
                self.assertIsNone(items[0]['expected_output'])
        with patch('backend.deepeval_generation.stream_chat', side_effect=SDKFixture()):
            items = generate_items([], 2, self.config, 'key', DEFAULT_PROMPT, [],
                                   GenerationOptions(method='scratch', task='Product questions', num_evolutions=0).model_dump())
        self.assertEqual(len(items), 2)
        self.assertIsNone(items[0]['expected_output'])
        self.assertIsNone(items[0]['context'])

    def test_adapter_rejects_invalid_schema_output(self):
        from deepeval.synthesizer.schema import InputFeedback
        with patch('backend.deepeval_generation.stream_chat', return_value=({}, '{"score":"invalid"}')):
            with self.assertRaises(ValueError):
                WorkspaceLLM(self.config, 'private').generate('evaluate', InputFeedback)


class GoldenApiTests(unittest.TestCase):
    setUp = dataset_fixtures.DatasetApiTests.setUp
    create = dataset_fixtures.DatasetApiTests.create
    def test_full_schema_export_in_all_formats(self):
        identifier = self.create()
        values = GoldenSchemaTests().golden().model_dump(mode='json')
        path = '/api/datasets/' + identifier
        self.assertEqual(self.client.post(path + '/items', json=values).status_code, 201)
        for suffix in ('json', 'jsonl', 'csv'):
            result = self.client.get(path + '/export?format=' + suffix)
            self.assertEqual(result.status_code, 200)
            imported = parse_import('export.' + suffix, result.content)[0]
            self.assertEqual(golden_dict(imported), values)
        sdk_values = self.client.get(path + '/export').json()
        self.assertEqual(sdk_values, [values])

    def test_seed_snapshot_ignores_archived_and_survives_seed_deletion(self):
        seed = self.create()
        self.repo.add(seed, [DatasetItem(input='active', context=['ctx']).model_dump(),
                             DatasetItem(input='archived', status='archived').model_dump()])
        opts = {'method': 'goldens', 'seed_dataset_id': seed, 'llm': self.selection, 'size': 1, 'num_evolutions': 0}
        with patch('backend.deepeval_generation.stream_chat', side_effect=SDKFixture()):
            result = self.client.post('/api/datasets/generate', data={'name': 'Expanded', 'options': json.dumps(opts)})
        self.assertEqual(result.status_code, 202)
        identifier = result.json()['id']
        self.assertEqual(self.repo.get(identifier)['status'], 'ready')
        self.assertEqual(len(self.repo.sources(identifier)), 1)
        self.repo.delete(seed)
        self.assertEqual(self.repo.sources(identifier)[0]['golden']['context'], ['ctx'])
        self.assertEqual(self.repo.items(identifier)['total'], 1)

    def test_scratch_has_no_files_or_answers_and_missing_task_is_rejected(self):
        opts = {'method': 'scratch', 'task': 'RAG questions', 'llm': self.selection, 'size': 2, 'num_evolutions': 0}
        with patch('backend.deepeval_generation.stream_chat', side_effect=SDKFixture()):
            result = self.client.post('/api/datasets/generate', data={'name': 'Scratch', 'options': json.dumps(opts)})
        self.assertEqual(result.status_code, 202)
        identifier = result.json()['id']
        self.assertEqual(self.repo.get(identifier)['status'], 'ready')
        self.assertIsNone(self.repo.items(identifier)['items'][0]['expected_output'])
        self.assertGreater(self.repo.get(identifier)['generation_usage']['requests'], 0)
        opts['task'] = ''
        self.assertEqual(self.client.post('/api/datasets/generate', data={'name': 'invalid', 'options': json.dumps(opts)}).status_code, 400)
