import { useEffect, useState } from 'react';
import { RotateCcw, Save } from 'lucide-react';
import type { Catalog } from '../types';
import { tr, type Language } from '../i18n';
import { datasetApi, llmChoices, selectionValue } from '../datasetApi';
import { SearchableSelect } from './SearchableSelect';

export function DatasetSettings({ catalog, language, readOnly }: { catalog: Catalog | null; language: Language; readOnly: boolean }) {
  const t = (value: string) => tr(language, value);
  const [selected, setSelected] = useState('');
  const [prompt, setPrompt] = useState('');
  const [defaultPrompt, setDefaultPrompt] = useState('');
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  const choices = llmChoices(catalog, language);
  const stale = !!selected && !choices.some(choice => choice.value === selected);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    datasetApi.settings().then(value => { if (active) { setSelected(selectionValue(value.default_llm)); setPrompt(value.prompt); setDefaultPrompt(value.default_prompt); setLoaded(true); } })
      .catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  return <section className="panel system-settings-panel dataset-settings-panel">
    <div className="panel-head"><div><h2>{t('数据集构建')}</h2><p>{t('为文档和 Dify 知识库生成评测问答，可在构建时覆盖默认模型。')}</p></div></div>
    <form className="system-settings-form" onSubmit={async event => {
      event.preventDefault(); if (readOnly) return; setBusy(true); setError(''); setSaved(false);
      try { await datasetApi.saveSettings({ default_llm: selected ? JSON.parse(selected) : null, prompt: prompt === defaultPrompt ? null : prompt }); setSaved(true); }
      catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
      finally { setBusy(false); }
    }}>
      <div className="field"><label>{t('默认构建模型')}</label><SearchableSelect label={t('默认构建模型')} language={language} value={selected} disabled={readOnly || loading || busy} onChange={value => { setSelected(value); setSaved(false); }} options={[{ value: '', label: t('未设置（构建时选择）') }, ...choices]} />
        {stale && <small className="error-text" role="alert">{t('原默认模型已失效，请重新选择')}</small>}
        {!choices.length && <small className="field-help">{t('暂无已配置的 LLM，请先在模型供应商中添加。')}</small>}
      </div>
      <label className="field"><span>{t('构建提示词')}</span><textarea aria-label={t('构建提示词')} rows={13} maxLength={20000} required disabled={readOnly || loading || busy} value={prompt} onChange={event => { setPrompt(event.target.value); setSaved(false); }} /><small className="field-help">{t('提示词作为 DeepEval 的生成任务要求；输出结构由 SDK 控制。修改后保存生效。')}</small></label>
      {error && <div className="alert" role="alert">{error}{!loaded && <button type="button" onClick={() => setReload(value => value + 1)}>{t('重试')}</button>}</div>}
      {saved && <p className="success-text" role="status">{t('空间配置已保存')}</p>}
      {!readOnly && <div className="dataset-actions"><button type="button" className="ghost" disabled={!loaded || loading || busy || prompt === defaultPrompt} onClick={() => { setPrompt(defaultPrompt); setSaved(false); }}><RotateCcw aria-hidden="true" />{t('恢复默认提示词')}</button><button className="primary compact" disabled={!loaded || loading || busy || stale || !prompt.trim()}><Save aria-hidden="true" />{t(busy ? '保存中…' : '保存配置')}</button></div>}
    </form>
  </section>;
}
