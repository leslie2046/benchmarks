import { useEffect, useState } from 'react';
import { ArrowLeft, Database, Download, FileUp, Pencil, Plus, RefreshCw, Search, Sparkles, Trash2 } from 'lucide-react';
import type { Catalog, Dataset, DatasetItem, DatasetSettings } from '../types';
import type { PageResult } from '../pagination';
import { datasetApi, downloadBlob, llmChoices, selectionValue } from '../datasetApi';
import { tr, type Language } from '../i18n';
import { Pagination } from './Pagination';
import { WorkspaceDialog } from './WorkspaceDialog';
import { SearchableSelect } from './SearchableSelect';
import '../datasets.css';

type Mode = 'import' | 'documents' | 'dify' | 'manual';
const sourceLabels = { import: '数据集导入', documents: '从文档生成', dify: '从Dify知识库生成', manual: '空白数据集', goldens: '种子扩写', scratch: '按任务生成' };
const statusLabels = { ready: '可用', generating: '构建中', failed: '构建失败' };
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
const renderValue = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '';
const emptyPage = <T,>(): PageResult<T> => ({ items: [], total: 0, page: 1, page_size: 10 });

export function Datasets({ catalog, language, onSettings }: { catalog: Catalog | null; language: Language; onSettings: () => void }) {
  const t = (value: string) => tr(language, value);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [list, setList] = useState(emptyPage<Dataset>);
  const [items, setItems] = useState(emptyPage<DatasetItem>);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [create, setCreate] = useState(false);
  const [editing, setEditing] = useState<DatasetItem | 'new' | null>(null);
  const [rename, setRename] = useState(false);
  const [exportFormat, setExportFormat] = useState<'json' | 'jsonl' | 'csv'>('json');
  const [append, setAppend] = useState(false);
  const [poll, setPoll] = useState(0);
  const id = dataset?.id;
  const generating = dataset?.status === 'generating';
  useEffect(() => { const timer = setTimeout(() => { setQuery(q); setPage(1); }, 250); return () => clearTimeout(timer); }, [q]);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setError('');
    const work = id ? Promise.all([datasetApi.get(id, controller.signal), datasetApi.items(id, page, size, query, controller.signal)]) : datasetApi.list(page, size, query, controller.signal);
    work.then(value => {
      if (!active) return;
      if (Array.isArray(value)) { setDataset(value[0]); setItems(value[1]); if (value[1].page !== page) setPage(value[1].page); }
      else { setList(value); if (value.page !== page) setPage(value.page); }
    }).catch(reason => { if (active && reason.name !== 'AbortError') setError(message(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [id, page, size, query, reload, poll]);
  useEffect(() => {
    if (!generating && (id || !list.items.some(value => value.status === 'generating'))) return;
    const timer = setInterval(() => setPoll(value => value + 1), 3000);
    return () => clearInterval(timer);
  }, [generating, id, list.items]);
  function open(value: Dataset | null) { setDataset(value); setItems(emptyPage()); setPage(1); setQ(''); setQuery(''); setError(''); }
  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); setReload(value => value + 1); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  const data = id ? items : list;
  return <section className="panel datasets-panel">
    <div className="panel-head dataset-heading"><div>
      {dataset && <button type="button" className="ghost dataset-back" onClick={() => open(null)}><ArrowLeft aria-hidden="true" />{t('所有数据集')}</button>}
      <h2>{dataset ? dataset.name : t('数据集')}</h2><p>{dataset ? dataset.description || t('问题、参考答案与参考上下文，用于后续 RAG 评测。') : t('管理 RAG 评测数据，从文档、已有数据集或 Dify 知识库开始。')}</p>
    </div><div className="dataset-actions">{dataset ? <>
      <select aria-label={t('导出格式')} value={exportFormat} onChange={event => setExportFormat(event.target.value as typeof exportFormat)}>{['json', 'jsonl', 'csv'].map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select>
      <button type="button" className="ghost" disabled={busy} onClick={() => void act(async () => downloadBlob(await datasetApi.export(dataset.id, exportFormat), `dataset-${dataset.id}.${exportFormat}`))}><Download aria-hidden="true" />{t('导出')}</button>
      <button type="button" className="ghost" disabled={busy || generating} onClick={() => setRename(true)}><Pencil aria-hidden="true" />{t('编辑')}</button>
      <button type="button" className="ghost" disabled={busy || generating} onClick={() => setAppend(true)}><FileUp aria-hidden="true" />{t('追加导入')}</button>
      <button type="button" className="primary compact" disabled={busy || generating} onClick={() => setEditing('new')}><Plus aria-hidden="true" />{t('添加数据项')}</button>
    </> : <button type="button" className="primary compact" onClick={() => setCreate(true)}><Plus aria-hidden="true" />{t('新建数据集')}</button>}</div></div>
    {dataset && <div className="dataset-summary"><DatasetStatus dataset={dataset} language={language} /><span>{t(sourceLabels[dataset.source_type])}</span><span>{dataset.item_count}{dataset.target_size ? ` / ${dataset.target_size}` : ''} {t('条数据')}</span>{dataset.source_chunk_count !== undefined && <span>{dataset.source_chunk_count} {t('个知识片段')}</span>}{dataset.llm && <span>{dataset.llm.model}</span>}{dataset.sdk && <span>DeepEval {dataset.sdk_version}</span>}{dataset.generation_usage && <span>{dataset.generation_usage.requests} {t('次模型请求')} · {dataset.generation_usage.output_tokens} {t('输出 tokens（已返回用量）')}</span>}</div>}
    {dataset?.error && <div className="dataset-feedback warning" role="alert"><span>{dataset.error}</span>{dataset.status === 'failed' && <button type="button" className="ghost" disabled={busy} onClick={() => void act(async () => setDataset(await datasetApi.retry(dataset.id)))}><RefreshCw aria-hidden="true" />{t('继续构建')}</button>}</div>}
    {generating && <div className="dataset-feedback" role="status"><Sparkles aria-hidden="true" /><span>{t('正在分批生成并保存问答，可离开此页面，进度会自动更新。')}</span><progress aria-label={t('构建进度')} value={dataset.item_count} max={dataset.target_size} /></div>}
    <div className="dataset-toolbar"><label className="dataset-search"><Search aria-hidden="true" /><input aria-label={t(id ? '搜索数据项' : '搜索数据集')} placeholder={t(id ? '搜索数据项' : '搜索数据集')} value={q} maxLength={200} onChange={event => setQ(event.target.value)} /></label><button type="button" className="ghost" disabled={loading} onClick={() => setReload(value => value + 1)}><RefreshCw aria-hidden="true" />{t('刷新')}</button></div>
    {error && <div className="dataset-feedback error" role="alert">{error}<button type="button" className="ghost" onClick={() => setReload(value => value + 1)}>{t('重试')}</button></div>}
    {loading && <p className="pagination-feedback" role="status">{t('加载中…')}</p>}
    <div className="dataset-table-wrap" aria-busy={loading}><table className="dataset-table"><thead>{dataset ? <tr><th>{t('输入 / 问题')}</th><th>{t('参考答案')}</th><th>{t('参考上下文')}</th><th>{t('状态')}</th><th>{t('操作')}</th></tr> : <tr><th>{t('名称')}</th><th>{t('来源')}</th><th>{t('数据项')}</th><th>{t('状态')}</th><th>{t('更新时间')}</th><th>{t('操作')}</th></tr>}</thead><tbody>
      {dataset ? items.items.map(item => <tr key={item.id}><td><button className="dataset-cell-button" type="button" onClick={() => setEditing(item)}><span className="dataset-cell-preview">{renderValue(item.input)}</span></button></td><td><span className="dataset-cell-preview">{renderValue(item.expected_output)}</span></td><td>{(item.context?.length || 0)} {t('个片段')}</td><td>{t(item.status === 'active' ? '启用' : '归档')}</td><td><div className="dataset-row-actions"><button type="button" className="icon-button" aria-label={t('查看或编辑数据项')} onClick={() => setEditing(item)}><Pencil aria-hidden="true" /></button><button type="button" className="icon-button" aria-label={t('删除数据项')} disabled={busy || generating} onClick={() => { if (window.confirm(t('确认删除这条数据项？'))) void act(() => datasetApi.deleteItem(dataset.id, item.id)); }}><Trash2 aria-hidden="true" /></button></div></td></tr>) : list.items.map(value => <tr key={value.id}><td><button type="button" className="dataset-cell-button" onClick={() => open(value)}><strong>{value.name}</strong><small>{value.description}</small></button></td><td>{t(sourceLabels[value.source_type])}</td><td>{value.item_count}{value.status === 'generating' ? ` / ${value.target_size}` : ''}</td><td><DatasetStatus dataset={value} language={language} /></td><td>{new Date(value.updated_at).toLocaleString(language)}</td><td><button type="button" className="icon-button" aria-label={`${t('删除数据集')} ${value.name}`} disabled={busy || value.status === 'generating'} onClick={() => { if (window.confirm(`${t('确认删除数据集及其所有数据项？')} ${value.name}`)) void act(() => datasetApi.delete(value.id)); }}><Trash2 aria-hidden="true" /></button></td></tr>)}
    </tbody></table></div>
    {!loading && !error && !data.items.length && <div className="empty-state"><Database aria-hidden="true" /><p>{t(q ? '没有匹配的数据，请调整搜索条件。' : id ? '暂无数据项，可手动添加或导入数据集。' : '暂无数据集，导入已有数据或让 AI 从知识内容生成。')}</p></div>}
    <Pagination page={data.page} pageSize={size} total={data.total} language={language} label={t(id ? '数据项' : '数据集')} onPageChange={setPage} onPageSizeChange={value => { setSize(value); setPage(1); }} disabled={loading} />
    {create && <CreateDataset catalog={catalog} language={language} onClose={() => setCreate(false)} onCreated={value => { setCreate(false); open(value); setReload(n => n + 1); }} onSettings={() => { setCreate(false); onSettings(); }} />}
    {editing && dataset && <ItemEditor item={editing === 'new' ? null : editing} dataset={dataset} language={language} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setReload(value => value + 1); }} />}
    {rename && dataset && <DatasetMetadata dataset={dataset} language={language} onClose={() => setRename(false)} onSaved={value => { setDataset(value); setRename(false); }} />}
    {append && dataset && <ImportItems dataset={dataset} language={language} onClose={() => setAppend(false)} onSaved={() => { setAppend(false); setReload(value => value + 1); }} />}
  </section>;
}

function DatasetStatus({ dataset, language }: { dataset: Dataset; language: Language }) {
  return <span className={`status status-${dataset.status === 'ready' ? 'completed' : dataset.status === 'generating' ? 'running' : 'failed'}`}><i />{tr(language, statusLabels[dataset.status])}</span>;
}

function ImportHelp({ language }: { language: Language }) {
  const t = (value: string) => tr(language, value);
  return <div className="dataset-import-help"><p>{t('支持 DeepEval Golden 的 CSV、JSON、JSONL，最多 10 MB / 20000 条，导出可直接加载为 Golden。')}</p><p>{t('标准字段为 input、expected_output、context、additional_metadata；也兼容旧字段，并保留工具调用、标签和检索结果。')}</p><button type="button" className="ghost" onClick={() => downloadBlob(new Blob([JSON.stringify([{ input: 'PrismLab 是什么？', expected_output: 'AI 模型测试与分析平台。', context: ['PrismLab 是 AI 模型测试与分析平台。'], additional_metadata: { source: 'example' } }], null, 2)], { type: 'application/json' }), 'dataset-example.json')}><Download aria-hidden="true" />{t('下载导入示例')}</button></div>;
}

function CreateDataset({ catalog, language, onClose, onCreated, onSettings }: { catalog: Catalog | null; language: Language; onClose: () => void; onCreated: (dataset: Dataset) => void; onSettings: () => void }) {
  const t = (value: string) => tr(language, value);
  const [mode, setMode] = useState<Mode>('import');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [size, setSize] = useState(50);
  const [ai, setAi] = useState(false);
  const [seed, setSeed] = useState('');
  const [seeds, setSeeds] = useState<Dataset[]>([]);
  const [advanced, setAdvanced] = useState(defaultGenerationOptions);

  const [llm, setLlm] = useState('');
  const [dify, setDify] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [settings, setSettings] = useState<DatasetSettings | null>(null);
  const [settingsError, setSettingsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const choices = llmChoices(catalog, language);
  const difyChoices = catalog?.benchmarks.find(value => value.id === 'dify-retrieve')?.providers || [];
  const generate = mode === 'documents' || mode === 'dify' || ai;
  const method = mode === 'import' && ai ? 'goldens' : mode === 'manual' && ai ? 'scratch' : 'contexts';
  const needsFiles = mode === 'documents' || (mode === 'import' && !ai);
  useEffect(() => {
    if (method !== 'goldens') return;
    let active = true;
    (async () => {
      const first = await datasetApi.list(1, 100, '');
      const values = [...first.items];
      for (let p = 2; p <= Math.ceil(first.total / 100); p++) values.push(...(await datasetApi.list(p, 100, '')).items);
      if (active) setSeeds(values.filter(value => value.status !== 'generating' && value.item_count > 0));
    })().catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [method]);
  const staleDefault = !!settings?.default_llm && !choices.some(value => value.value === selectionValue(settings.default_llm));
  useEffect(() => {
    let active = true;
    datasetApi.settings().then(value => { if (active) setSettings(value); }).catch(reason => { if (active) setSettingsError(message(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return <WorkspaceDialog title={t('新建数据集')} language={language} busy={busy} onClose={onClose}><form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let value: Dataset;
      if (mode === 'manual' && !ai) value = await datasetApi.create({ name, description });
      else {
        const form = new FormData(); form.set('name', name); form.set('description', description);
        if (mode === 'import' && !ai) { form.set('file', files[0]); value = await datasetApi.import(form); }
        else { form.set('options', JSON.stringify({ ...advanced, size, method, seed_dataset_id: method === 'goldens' ? seed : null, critic_llm: advanced.critic_llm ? JSON.parse(advanced.critic_llm) : null, llm: llm ? JSON.parse(llm) : null, dify_config_id: mode === 'dify' ? dify : null, language })); files.forEach(file => form.append('files', file)); value = await datasetApi.generate(form); }
      }
      onCreated(value);
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }}><div className="workspace-dialog-body dataset-create-body">
    <div className="dataset-source-tabs" role="group" aria-label={t('数据来源')}>{(['import', 'documents', 'dify', 'manual'] as Mode[]).map(value => <button type="button" key={value} aria-pressed={mode === value} disabled={busy} onClick={() => { setMode(value); setFiles([]); setAi(false); setError(''); }}>{t(sourceLabels[value])}</button>)}</div>
    <label className="field"><span>{t('数据集名称')}</span><input autoFocus required maxLength={120} value={name} disabled={busy} onChange={event => setName(event.target.value)} /></label>
    <label className="field"><span>{t('描述')}</span><textarea rows={2} maxLength={2000} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} /></label>
    {(mode === 'import' || mode === 'manual') && <label className="dataset-check"><input type="checkbox" checked={ai} disabled={busy} onChange={event => { setAi(event.target.checked); setFiles([]); }} />{t(mode === 'import' ? '使用 AI 扩写已有数据集' : '使用 AI 按任务生成')}</label>}
    {method === 'goldens' && <div className="field"><label>{t('种子数据集')}</label><SearchableSelect label={t('种子数据集')} language={language} disabled={busy} value={seed} onChange={setSeed} options={seeds.map(value => ({ value: value.id, label: `${value.name} · ${value.item_count}` }))} /><small className="field-help">{t('使用启用的 Golden 作为种子；没有 context 时仅生成问题。有无上下文的种子需分开。')}</small></div>}
    {needsFiles && <label className="field"><span>{t(mode === 'import' ? '数据集文件' : '源文档')}</span><input aria-label={t(mode === 'import' ? '数据集文件' : '源文档')} key={mode} type="file" required multiple={mode === 'documents'} accept={mode === 'import' ? '.json,.jsonl,.csv' : '.txt,.md,.markdown,.pdf,.docx,.csv'} disabled={busy} onChange={event => { const next = Array.from(event.target.files || []); setFiles(next); setError(next.reduce((sum, file) => sum + file.size, 0) > 10 * 1024 * 1024 ? t('文件总大小不能超过 10 MB') : ''); }} /><small className="field-help">{t(mode === 'import' ? '导入已有问答和参考上下文，不调用模型。' : '支持 TXT、Markdown、PDF、DOCX、CSV，最多 20 个文件 / 10 MB；扫描 PDF 需先 OCR。')}</small></label>}
    {mode === 'import' && !ai && <ImportHelp language={language} />}
    {mode === 'dify' && <div className="field"><label>{t('Dify 知识库')}</label><SearchableSelect label={t('Dify 知识库')} language={language} disabled={busy} value={dify} onChange={setDify} options={difyChoices.map(value => ({ value: value.id, label: `${value.label} · ${value.dataset_id || t('未配置')}` }))} /><small className="field-help">{t('使用 Dify 配置中的知识库 ID 和 Dataset API Key，自动分页拉取已启用的文档分段。')}</small></div>}
    {generate && <><label className="field"><span>{t('目标数据集大小')}</span><input aria-label={t('目标数据集大小')} required type="number" min={1} max={500} step={1} disabled={busy} value={size} onChange={event => setSize(Number(event.target.value))} /><small className="field-help">{t('1–500 条问答；有效数据不足时保留已有结果并提示重试。')}</small></label>
      <div className="field"><label>{t('生成模型')}</label><SearchableSelect label={t('生成模型')} language={language} disabled={busy} value={llm} onChange={setLlm} options={[{ value: '', label: t('使用空间默认模型') + (settings?.default_llm ? ` · ${settings.default_llm.model}` : ` · ${t('未配置')}`) }, ...choices]} /><small className="field-help">{t('会调用所选 LLM 并产生相应费用。')}</small>{!llm && staleDefault && <small className="error-text">{t('原默认模型已失效，请重新选择')}</small>}</div>
      <GenerationControls value={advanced} onChange={setAdvanced} catalog={catalog} language={language} disabled={busy} scratch={method === 'scratch'} />
      {settingsError && <p className="error-text" role="alert">{settingsError}</p>}
      <button type="button" className="ghost dataset-settings-link" disabled={busy} onClick={onSettings}>{t('设置默认模型与构建提示词')}</button>
    </>}
    {error && <p className="error-text" role="alert">{error}</p>}
  </div><div className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t('取消')}</button><button className="primary compact" disabled={busy || !name.trim() || (needsFiles && (!files.length || files.reduce((sum, file) => sum + file.size, 0) > 10 * 1024 * 1024)) || (method === 'goldens' && !seed) || (method === 'scratch' && !advanced.task.trim()) || (mode === 'dify' && !dify) || (generate && (!llm && (loading || !settings?.default_llm || staleDefault)))}>{generate ? <Sparkles aria-hidden="true" /> : <FileUp aria-hidden="true" />}{t(busy ? '提交中…' : generate ? '开始构建' : mode === 'manual' ? '创建' : '导入数据集')}</button></div></form></WorkspaceDialog>;
}

const defaultGenerationOptions = {
  critic_llm: '', include_expected_output: true, quality_threshold: 0.5, max_quality_retries: 3,
  num_evolutions: 1, max_concurrent: 3, context_size: 2,
  evolutions: { CONCRETIZING: 1, CONSTRAINED: 1, COMPARATIVE: 1 } as Record<string, number>,
  task: '', scenario: '', input_format: '', expected_output_format: '',
};
const evolutionLabels: Record<string, string> = { REASONING: '推理', MULTICONTEXT: '多上下文', CONCRETIZING: '具体化', CONSTRAINED: '增加约束', COMPARATIVE: '比较', HYPOTHETICAL: '假设', IN_BREADTH: '拓宽主题' };
function GenerationControls({ value, onChange, catalog, language, disabled, scratch }: { value: typeof defaultGenerationOptions; onChange: (value: typeof defaultGenerationOptions) => void; catalog: Catalog | null; language: Language; disabled: boolean; scratch: boolean }) {
  const t = (text: string) => tr(language, text);
  const change = (key: keyof typeof value, next: unknown) => onChange({ ...value, [key]: next });
  return <>
    {scratch && <label className="field"><span>{t('生成任务')}</span><textarea aria-label={t('生成任务')} required rows={3} maxLength={2000} value={value.task} disabled={disabled} onChange={event => change('task', event.target.value)} /><small className="field-help">{t('无资料生成仅产生问题，不生成参考答案。')}</small></label>}
    <details className="dataset-advanced"><summary>{t('DeepEval 高级配置')}</summary><div className="dataset-advanced-fields">
      <div className="field"><label>{t('质量评审模型')}</label><SearchableSelect label={t('质量评审模型')} language={language} disabled={disabled} value={value.critic_llm} onChange={next => change('critic_llm', next)} options={[{ value: '', label: t('与生成模型相同') }, ...llmChoices(catalog, language)]} /></div>
      <div className="dataset-option-grid">{([
        ['quality_threshold', '质量阈值', 0, 1, 0.05], ['max_quality_retries', '质量评审次数上限', 1, 5, 1],
        ['num_evolutions', '演化轮数', 0, 3, 1], ['max_concurrent', '模型并发上限', 1, 10, 1], ['context_size', '每组上下文片段数', 1, 5, 1],
      ] as const).map(([key, label, min, max, step]) => <label key={key} className="field"><span>{t(label)}</span><input type="number" required min={min} max={max} step={step} disabled={disabled} value={value[key]} onChange={event => change(key, Number(event.target.value))} /></label>)}</div>
      <p className="field-help">{t('演化权重（0 为禁用，按比例抽样）')}</p>
      <div className="dataset-option-grid">{Object.entries(evolutionLabels).map(([key, label]) => <label className="field" key={key}><span>{t(label)}</span><input type="number" required min={0} max={100} step={1} disabled={disabled} value={value.evolutions[key] || 0} onChange={event => change('evolutions', { ...value.evolutions, [key]: Number(event.target.value) })} /></label>)}</div>
      <p className="field-help">{t('默认采用有资料依据的演化方式。推理、假设和拓宽主题可能超出资料；多上下文需至少两个片段。')}</p>
      <p className="field-help">{t('DeepEval 达到评审次数上限后仍可能保留低分项；质量分与待复核标记保存在 additional_metadata。')}</p>
      {!scratch && <label className="dataset-check"><input type="checkbox" checked={value.include_expected_output} disabled={disabled} onChange={event => change('include_expected_output', event.target.checked)} />{t('生成参考答案')}</label>}
      {(['task', 'scenario', 'input_format', 'expected_output_format'] as const).filter(key => !scratch || key !== 'task').map(key => <label className="field" key={key}><span>{t({ task: '生成任务', scenario: '应用场景', input_format: '问题风格', expected_output_format: '答案风格' }[key])}</span><textarea rows={2} maxLength={2000} disabled={disabled} value={value[key]} onChange={event => change(key, event.target.value)} /></label>)}
    </div></details>
  </>;
}

function ItemEditor({ item, dataset, language, onClose, onSaved }: { item: DatasetItem | null; dataset: Dataset; language: Language; onClose: () => void; onSaved: () => void }) {
  const t = (value: string) => tr(language, value);
  const { id: _id, dataset_id: _datasetId, created_at: _created, updated_at: _updated, status: _status, ...golden } = item || {};
  const [content, setContent] = useState(JSON.stringify(item ? golden : { input: '', expected_output: null, context: [], additional_metadata: {} }, null, 2));
  const [status, setStatus] = useState(item?.status || 'active');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const readOnly = dataset.status === 'generating';
  return <WorkspaceDialog title={t(item ? '查看或编辑数据项' : '添加数据项')} language={language} busy={busy} onClose={onClose}><form onSubmit={async event => {
    event.preventDefault(); setError('');
    let value;
    try {
      const record = JSON.parse(content);
      if (!record || Array.isArray(record) || typeof record.input !== 'string' || !record.input.trim()) throw new Error();
      value = { ...record, status };
    } catch { setError(t('请填写有效的 Golden JSON，input 必须为非空字符串。')); return; }
    setBusy(true);
    try { await datasetApi.saveItem(dataset.id, item?.id, value); onSaved(); }
    catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }}><div className="workspace-dialog-body dataset-item-body"><p className="workspace-muted">{t('使用 DeepEval Golden JSON 编辑全部字段。context 是参考上下文，retrieval_context 是实际检索结果。')}</p>
    <label className="field"><span>Golden JSON</span><textarea aria-label="Golden JSON" className="dataset-json" rows={20} required value={content} disabled={busy || readOnly} onChange={event => setContent(event.target.value)} /></label>
    <label className="field"><span>{t('状态')}</span><select disabled={busy || readOnly} value={status} onChange={event => setStatus(event.target.value as 'active' | 'archived')}><option value="active">{t('启用')}</option><option value="archived">{t('归档')}</option></select></label>
    {error && <p className="error-text" role="alert">{error}</p>}
  </div><div className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t('关闭')}</button>{!readOnly && <button className="primary compact" disabled={busy}>{t(busy ? '保存中…' : '保存')}</button>}</div></form></WorkspaceDialog>;
}

function DatasetMetadata({ dataset, language, onClose, onSaved }: { dataset: Dataset; language: Language; onClose: () => void; onSaved: (value: Dataset) => void }) {
  const t = (value: string) => tr(language, value);
  const [name, setName] = useState(dataset.name), [description, setDescription] = useState(dataset.description);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <WorkspaceDialog title={t('编辑数据集')} language={language} busy={busy} onClose={onClose}><form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { onSaved(await datasetApi.update(dataset.id, { name, description })); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } }}><div className="workspace-dialog-body"><label className="field"><span>{t('名称')}</span><input required maxLength={120} disabled={busy} value={name} onChange={event => setName(event.target.value)} /></label><label className="field"><span>{t('描述')}</span><textarea rows={3} maxLength={2000} disabled={busy} value={description} onChange={event => setDescription(event.target.value)} /></label>{error && <p role="alert" className="error-text">{error}</p>}</div><div className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t('取消')}</button><button className="primary compact" disabled={busy || !name.trim()}>{t(busy ? '保存中…' : '保存')}</button></div></form></WorkspaceDialog>;
}

function ImportItems({ dataset, language, onClose, onSaved }: { dataset: Dataset; language: Language; onClose: () => void; onSaved: () => void }) {
  const t = (value: string) => tr(language, value);
  const [file, setFile] = useState<File | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <WorkspaceDialog title={t('追加导入')} language={language} busy={busy} onClose={onClose}><form onSubmit={async event => { event.preventDefault(); if (!file) return; setBusy(true); setError(''); try { const form = new FormData(); form.set('file', file); await datasetApi.append(dataset.id, form); onSaved(); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } }}><div className="workspace-dialog-body"><ImportHelp language={language} /><label className="field"><span>{t('数据集文件')}</span><input required type="file" accept=".csv,.json,.jsonl" disabled={busy} onChange={event => setFile(event.target.files?.[0] || null)} /></label>{file && file.size > 10 * 1024 * 1024 && <p className="error-text">{t('文件总大小不能超过 10 MB')}</p>}{error && <p className="error-text" role="alert">{error}</p>}</div><div className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t('取消')}</button><button className="primary compact" disabled={busy || !file || file.size > 10 * 1024 * 1024}>{t(busy ? '提交中…' : '追加导入')}</button></div></form></WorkspaceDialog>;
}
