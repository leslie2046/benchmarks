"""Local DeepEval Synthesizer pipeline using PrismLab's existing model credentials."""
import asyncio
import json
import re
import threading

from backend.dataset_golden import DatasetItem, Golden
from deepeval.models import DeepEvalBaseLLM
from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import EvolutionConfig, FiltrationConfig, StylingConfig
from deepeval.synthesizer.types import Evolution
from deepeval.synthesizer.templates import ExtractionTemplate
from deepeval.synthesizer.schema import PromptStyling
from shared.llm_stream import stream_chat


class WorkspaceLLM(DeepEvalBaseLLM):
    """Schema-capable adapter; all requests use the selected workspace endpoint."""
    def __init__(self, config, key, usage=None):
        self.config, self.key = config, key
        self.usage = usage if usage is not None else {'requests': 0, 'output_tokens': 0}
        self._lock = threading.Lock()
        super().__init__(model=config['model'])

    def load_model(self):
        return self.config

    def get_model_name(self):
        return self.config['model']

    def generate(self, prompt, schema=None):
        if schema is not None:
            prompt += '\n\nReturn only a JSON object matching this JSON Schema. No Markdown.\n' + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        with self._lock:
            self.usage['requests'] += 1
        sample, content = stream_chat(self.config['base_url'], self.config['model'], self.key, prompt,
                                      max_tokens=8192, timeout=180, capture=True,
                                      capture_reasoning=False, require_complete=True)
        with self._lock:
            self.usage['output_tokens'] += sample.get('output_tokens', 0)
        if schema is None:
            return content
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
        return schema.model_validate_json(content)

    async def a_generate(self, prompt, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)


def generate_items(chunks, count, config, key, prompt, existing, options=None, critic=None, usage=None):
    opts = options or {}
    model = WorkspaceLLM(config, key, usage)
    critic_model = WorkspaceLLM(*critic, usage=usage) if critic else model
    weights = opts.get('evolutions', {'CONCRETIZING': 1, 'CONSTRAINED': 1, 'COMPARATIVE': 1})
    total = sum(weights.values())
    language = '中文' if opts.get('language', 'zh-CN') == 'zh-CN' else 'English'
    task = prompt + '\n' + opts.get('task', '') + '\n生成语言 / Language: ' + language
    if existing:
        task += '\nAvoid duplicating these existing inputs:\n' + json.dumps(existing[-100:], ensure_ascii=False)
    synth = Synthesizer(model=model, async_mode=True, max_concurrent=opts.get('max_concurrent', 3),
                        filtration_config=FiltrationConfig(critic_model=critic_model,
                            synthetic_input_quality_threshold=opts.get('quality_threshold', 0.5),
                            max_quality_retries=opts.get('max_quality_retries', 3)),
                        evolution_config=EvolutionConfig(num_evolutions=opts.get('num_evolutions', 1),
                            evolutions={Evolution[k]: v / total for k, v in weights.items()}),
                        styling_config=StylingConfig(task=task, scenario=opts.get('scenario') or 'RAG evaluation',
                            input_format=opts.get('input_format') or 'A standalone user question',
                            expected_output_format=opts.get('expected_output_format') or None))

    async def run():
        method = opts.get('method', 'contexts')
        if method == 'scratch':
            return await synth.a_generate_goldens_from_scratch(num_goldens=count)
        if method == 'goldens':
            seeds = [Golden.model_validate(c['golden']) for c in chunks]
            # Use the SDK's seed-style extraction while retaining workspace instructions.
            styles = await model.a_generate(ExtractionTemplate.extract_prompt_structure_from_inputs(
                [g.input for g in seeds]), schema=PromptStyling)
            synth.styling_config = StylingConfig(
                task=styles.task + '\n' + task,
                scenario=opts.get('scenario') or styles.scenario,
                input_format=opts.get('input_format') or styles.input_format,
                expected_output_format=opts.get('expected_output_format') or None)
            return await synth.a_generate_goldens_from_goldens(
                goldens=seeds,
                max_goldens_per_golden=count,
                include_expected_output=opts.get('include_expected_output', True))
        sources = [c['metadata'].get('filename') or c['metadata'].get('document_name') or c['id'] for c in chunks]
        return await synth.a_generate_goldens_from_contexts(
            contexts=[[c['content'] for c in chunks]], source_files=[sources],
            context_chunk_source_files=[sources], max_goldens_per_context=count,
            include_expected_output=opts.get('include_expected_output', True))

    # Async SDK methods return records locally and do not call the cloud upload helper.
    goldens = asyncio.run(run())
    seen = {re.sub(r'\s+', '', value).casefold() for value in existing}
    result = []
    for golden in goldens:
        normalized = re.sub(r'\s+', '', golden.input).casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        metadata = dict(golden.additional_metadata or {})
        score = metadata.get('synthetic_input_quality')
        metadata['prismlab_generation'] = {
            'sdk': 'deepeval', 'sdk_version': '4.3.2', 'method': opts.get('method', 'contexts'),
            'sources': [c.get('metadata', {}) for c in chunks],
            'quality_threshold': opts.get('quality_threshold', 0.5),
            'review_required': score is None or score < opts.get('quality_threshold', 0.5),
        }
        golden.additional_metadata = metadata
        result.append(DatasetItem.model_validate(golden.model_dump(mode='json')).model_dump(mode='json'))
        if len(result) >= count:
            break
    return result
