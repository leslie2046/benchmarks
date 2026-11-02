import csv
import io
import json

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from backend.dataset_store import DatasetStore
from backend.datasets import (DEFAULT_PROMPT, LEGACY_DEFAULT_PROMPT, MAX_UPLOAD, DatasetInfo, DatasetItem, DatasetSettings,
                              GenerationOptions, build_dataset, document_chunks, parse_import)
from backend.dataset_golden import golden_dict
from deepeval.dataset.utils import join_context, join_retrieval_context
from backend.schemas import PlaygroundRequest, ProviderSelection
from backend.model_configs import configured_models


def install_dataset_routes(app, store, resolve_access, concrete_store):
    router = APIRouter(prefix='/api', tags=['datasets'])

    def repo():
        return DatasetStore(concrete_store())

    def settings():
        value = store.system_settings()
        prompt = value.get('dataset_prompt')
        if prompt == LEGACY_DEFAULT_PROMPT:
            prompt = None
        return {'default_llm': value.get('dataset_default_llm'),
                'prompt': prompt or DEFAULT_PROMPT, 'default_prompt': DEFAULT_PROMPT,
                'sdk': 'deepeval', 'sdk_version': '4.3.2'}

    def llm_access(selection):
        credential_id = selection.get('credential_id')
        if credential_id == 'legacy':
            saved = store.get_service_config(selection['id'])
            models = configured_models(saved) if saved else []
            selected = next((m for m in models if m['benchmark'] == 'llm' and selection.get('model') in {m.get('alias'), m.get('name')}), None)
            if selected and not selected.get('credentials'):
                credential_id = None  # Public catalogs synthesize a credential for old endpoint-only records.
        return resolve_access(PlaygroundRequest(benchmark='llm', provider_id=selection['id'],
                              model=selection.get('model'), credential_id=credential_id, query='generate dataset'))

    def resolve_llm(selection):
        if not selection:
            raise HTTPException(400, '请先在空间设置中选择构建数据集的默认 LLM，或在此处选择模型')
        selection = ProviderSelection.model_validate(selection).model_dump()
        config, key = llm_access(selection)
        models = [model for model in configured_models(config) if model['benchmark'] == 'llm']
        model = next((model for model in models if selection.get('model') in {model.get('alias'), model.get('name')}), None)
        model = model or (models[0] if models else None)
        credential_id = config.get('credential_id')
        if model and not model.get('credentials') and model.get('base_url'):
            credential_id = 'legacy'
        selection.update(credential_id=credential_id, model=(model.get('alias') or model['name']) if model else config['model'])
        return selection, config, key

    def dify_access(config_id):
        if not config_id:
            raise HTTPException(400, '请选择 Dify 知识库配置')
        config = store.get_service_config(config_id)
        if not config or config.get('provider') != 'dify':
            raise HTTPException(400, 'Dify 配置不存在')
        resolved, key = resolve_access(PlaygroundRequest(benchmark='dify-retrieve', provider_id=config_id, query='dataset source'))
        return resolved, key

    async def read_upload(file):
        data = await file.read(MAX_UPLOAD + 1)
        if not data or len(data) > MAX_UPLOAD:
            raise HTTPException(400, '文件不能为空，且不能超过 10 MB')
        return data

    @router.get('/dataset-settings')
    def get_settings():
        return settings()

    @router.put('/dataset-settings')
    def save_settings(payload: DatasetSettings):
        selection = payload.default_llm.model_dump() if payload.default_llm else None
        if selection:
            selection, _, _ = resolve_llm(selection)
        store.save_system_settings({'dataset_default_llm': selection, 'dataset_prompt': payload.prompt})
        return settings()

    @router.get('/datasets')
    def list_datasets(page: int = Query(1, ge=1, le=1000000000), page_size: int = Query(10, ge=1, le=100), q: str = Query('', max_length=200)):
        return repo().page(page, page_size, q)

    @router.post('/datasets', status_code=201)
    def create_dataset(payload: DatasetInfo):
        return repo().create({**payload.model_dump(), 'source_type': 'manual'})

    @router.post('/datasets/import', status_code=201)
    async def import_dataset(name: str = Form(..., min_length=1, max_length=120), description: str = Form('', max_length=2000), file: UploadFile = File(...)):
        data = await read_upload(file)
        try:
            info = DatasetInfo(name=name, description=description)
            items = await run_in_threadpool(parse_import, file.filename or '', data)
        except (ValueError, RecursionError):
            # Do not expose source content embedded in parser/validation exceptions.
            raise HTTPException(400, '导入格式无效，请检查文件编码、列名和数据类型。支持 CSV、JSON、JSONL，input 必填。') from None
        target = repo()
        dataset = await run_in_threadpool(target.create, {**info.model_dump(), 'source_type': 'import', 'source_filename': file.filename})
        try:
            return await run_in_threadpool(target.add, dataset['id'], items)
        except Exception:
            await run_in_threadpool(target.delete, dataset['id'])
            raise

    @router.post('/datasets/generate', status_code=202)
    async def generate_dataset(background_tasks: BackgroundTasks, name: str = Form(..., min_length=1, max_length=120),
                               description: str = Form('', max_length=2000), options: str = Form(..., max_length=10000),
                               files: list[UploadFile] = File(default=[])):
        try:
            info = DatasetInfo(name=name, description=description)
            opts = GenerationOptions.model_validate_json(options)
        except ValueError:
            raise HTTPException(400, '构建参数无效，请检查大小（1–500）、质量与演化参数，以及种子数据集或生成任务') from None
        selection, config, key = resolve_llm(opts.llm.model_dump() if opts.llm else settings()['default_llm'])
        critic_selection, critic_config, critic_key = resolve_llm(opts.critic_llm.model_dump()) if opts.critic_llm else (None, None, None)
        if opts.dify_config_id and files:
            raise HTTPException(400, '请选择文档或 Dify 其中一种数据源')
        dify = dify_access(opts.dify_config_id) if opts.dify_config_id else None
        chunks = []
        total_bytes = 0
        target = repo()
        if opts.method != 'contexts' and files:
            raise HTTPException(400, '此生成方式不支持上传文档')
        if opts.method == 'goldens':
            # Reads use the current workspace store; cross-workspace IDs cannot resolve.
            seed = target.get(opts.seed_dataset_id)
            if seed['status'] == 'generating':
                raise HTTPException(409, '种子数据集正在构建，请稍后重试')
            chunks = [{'id': item['id'], 'golden': golden_dict(item),
                       'metadata': {'seed_dataset_id': opts.seed_dataset_id, 'seed_item_id': item['id']}}
                      for item in target.items(opts.seed_dataset_id, size=20000)['items'] if item['status'] == 'active']
            if not chunks:
                raise HTTPException(400, '种子数据集没有启用的数据项')
            has_context = [bool(c['golden'].get('context')) for c in chunks]
            if any(has_context) and not all(has_context):
                raise HTTPException(400, '种子项需全部包含参考上下文或全部不含上下文，请先整理种子数据集')
        elif opts.method == 'contexts' and not dify:
            if not files or len(files) > 20:
                raise HTTPException(400, '请上传 1–20 个文档')
            for index, file in enumerate(files):
                data = await read_upload(file)
                total_bytes += len(data)
                if total_bytes > MAX_UPLOAD:
                    raise HTTPException(400, '上传文件总大小不能超过 10 MB')
                try:
                    parts = await run_in_threadpool(document_chunks, file.filename or '', data)
                except Exception:
                    raise HTTPException(400, '无法解析文档。请使用 TXT、Markdown、非加密文本 PDF 或 DOCX；扫描件需先 OCR。') from None
                for part in parts:
                    part['id'] = f'file-{index + 1}-{part["id"]}'
                chunks.extend(parts)
            if sum(len(c['content']) for c in chunks) > 2_000_000:
                raise HTTPException(400, '文档总文本不能超过 200 万字符')
        generation_options = opts.model_dump(mode='json')
        generation_options.update(llm=selection, critic_llm=critic_selection)
        source_type = 'goldens' if opts.method == 'goldens' else 'scratch' if opts.method == 'scratch' else 'dify' if dify else 'documents'
        dataset = target.create({**info.model_dump(), 'status': 'generating', 'source_type': source_type,
                                 'target_size': opts.size, 'llm': selection, 'dify_config_id': opts.dify_config_id,
                                 'prompt': settings()['prompt'], 'source_chunk_count': len(chunks),
                                 'generation_options': generation_options, 'sdk': 'deepeval', 'sdk_version': '4.3.2'})
        try:
            target.save_sources(dataset['id'], chunks)
        except Exception:
            target.mutate(dataset['id'], lambda c, d: d.update(status='failed', error='资料保存失败，请重新构建。'), generating=True)
            raise
        background_tasks.add_task(build_dataset, target, dataset['id'], chunks, dify, config, key, dataset['prompt'],
                                  generation_options, (critic_config, critic_key) if critic_selection else None)
        return dataset

    @router.get('/datasets/{identifier}')
    def get_dataset(identifier: str):
        return repo().get(identifier)

    @router.put('/datasets/{identifier}')
    def update_dataset(identifier: str, payload: DatasetInfo):
        return repo().mutate(identifier, lambda c, d: d.update(**payload.model_dump()))

    @router.delete('/datasets/{identifier}', status_code=204)
    def delete_dataset(identifier: str):
        repo().delete(identifier)

    @router.post('/datasets/{identifier}/retry', status_code=202)
    def retry_dataset(identifier: str, background_tasks: BackgroundTasks):
        target = repo()
        dataset = target.get(identifier)
        if dataset['status'] != 'failed' or not dataset.get('target_size'):
            raise HTTPException(409, '只能重试未完成的数据集构建')
        selection, config, key = resolve_llm(dataset.get('llm') or settings()['default_llm'])
        dify = dify_access(dataset['dify_config_id']) if dataset.get('dify_config_id') else None
        chunks = target.sources(identifier)
        opts = dataset.get('generation_options', {})
        critic = resolve_llm(opts['critic_llm'])[1:] if opts.get('critic_llm') else None
        if opts.get('method') != 'scratch' and not dify and not chunks:
            raise HTTPException(400, '源文档不存在，请重新上传构建')
        def start(c, d):
            if d['status'] != 'failed':
                raise HTTPException(409, '数据集正在构建')
            d.update(status='generating', error=None, llm=selection)
        dataset = target.mutate(identifier, start)
        prompt = dataset.get('prompt') or settings()['prompt']
        if prompt == LEGACY_DEFAULT_PROMPT:
            prompt = DEFAULT_PROMPT
        background_tasks.add_task(build_dataset, target, identifier, chunks, dify, config, key, prompt, opts, critic)
        return dataset

    @router.get('/datasets/{identifier}/items')
    def list_items(identifier: str, page: int = Query(1, ge=1, le=1000000000), page_size: int = Query(20, ge=1, le=100), q: str = Query('', max_length=200)):
        return repo().items(identifier, page, page_size, q)

    @router.post('/datasets/{identifier}/items', status_code=201)
    def add_item(identifier: str, payload: DatasetItem):
        return repo().add(identifier, [payload.model_dump()])

    @router.put('/datasets/{identifier}/items/{item_id}')
    def update_item(identifier: str, item_id: str, payload: DatasetItem):
        return repo().update_item(identifier, item_id, payload.model_dump())

    @router.delete('/datasets/{identifier}/items/{item_id}', status_code=204)
    def delete_item(identifier: str, item_id: str):
        repo().update_item(identifier, item_id)

    @router.post('/datasets/{identifier}/import')
    async def append_import(identifier: str, file: UploadFile = File(...)):
        data = await read_upload(file)
        try:
            items = await run_in_threadpool(parse_import, file.filename or '', data)
        except (ValueError, RecursionError):
            raise HTTPException(400, '导入格式无效，请检查文件内容、列名和数据类型') from None
        return await run_in_threadpool(repo().add, identifier, items)

    @router.get('/datasets/{identifier}/export')
    def export_dataset(identifier: str, format: str = Query('json', pattern='^(json|jsonl|csv)$')):
        target = repo()
        dataset = target.get(identifier)
        items = [golden_dict(item) for item in target.items(identifier, size=20000)['items']]
        if format == 'csv':
            output = io.StringIO(newline='')
            fields = list(items[0]) if items else list(golden_dict({'input': 'example'}))
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for item in items:
                cells = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                         for key, value in item.items()}
                cells['context'] = join_context(item.get('context'))
                cells['retrieval_context'] = join_retrieval_context(item.get('retrieval_context'))
                writer.writerow(cells)
            content, media_type = '\ufeff' + output.getvalue(), 'text/csv'
        elif format == 'jsonl':
            content, media_type = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in items), 'application/x-ndjson'
        else:
            content, media_type = json.dumps(items, ensure_ascii=False, indent=2), 'application/json'
        return Response(content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="dataset-{identifier}.{format}"'})

    app.include_router(router)
