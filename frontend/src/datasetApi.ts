import { authenticatedFetch } from './api';
import type { Catalog, Dataset, DatasetItem, DatasetSettings, LlmSelection } from './types';
import type { PageResult } from './pagination';
import { providerDisplayName } from './providerPresets';
import type { Language } from './i18n';

async function call<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await authenticatedFetch(`/api/${path}`, { method, signal,
    ...(body === undefined ? {} : { headers: multipart ? {} : { 'Content-Type': 'application/json' }, body: multipart ? body : JSON.stringify(body) }),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    throw new Error(typeof value?.detail === 'string' ? value.detail : `Request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const datasetApi = {
  list: (page: number, size: number, q: string, signal?: AbortSignal) => call<PageResult<Dataset>>(`datasets?${new URLSearchParams({ page: String(page), page_size: String(size), q })}`, 'GET', undefined, signal),
  get: (id: string, signal?: AbortSignal) => call<Dataset>(`datasets/${id}`, 'GET', undefined, signal),
  items: (id: string, page: number, size: number, q: string, signal?: AbortSignal) => call<PageResult<DatasetItem>>(`datasets/${id}/items?${new URLSearchParams({ page: String(page), page_size: String(size), q })}`, 'GET', undefined, signal),
  create: (value: { name: string; description: string }) => call<Dataset>('datasets', 'POST', value),
  import: (form: FormData) => call<Dataset>('datasets/import', 'POST', form),
  generate: (form: FormData) => call<Dataset>('datasets/generate', 'POST', form),
  update: (id: string, value: { name: string; description: string }) => call<Dataset>(`datasets/${id}`, 'PUT', value),
  delete: (id: string) => call<void>(`datasets/${id}`, 'DELETE'),
  retry: (id: string) => call<Dataset>(`datasets/${id}/retry`, 'POST'),
  append: (id: string, form: FormData) => call<Dataset>(`datasets/${id}/import`, 'POST', form),
  saveItem: (id: string, itemId: string | undefined, value: unknown) => call<Dataset>(`datasets/${id}/items${itemId ? `/${itemId}` : ''}`, itemId ? 'PUT' : 'POST', value),
  deleteItem: (id: string, itemId: string) => call<void>(`datasets/${id}/items/${itemId}`, 'DELETE'),
  settings: () => call<DatasetSettings>('dataset-settings'),
  saveSettings: (value: { default_llm: LlmSelection | null; prompt: string | null }) => call<DatasetSettings>('dataset-settings', 'PUT', value),
  export: async (id: string, format: 'json' | 'jsonl' | 'csv' = 'json') => {
    const response = await authenticatedFetch(`/api/datasets/${id}/export?format=${format}`);
    if (!response.ok) throw new Error(`Export failed (${response.status})`);
    return response.blob();
  },
};
export function llmChoices(catalog: Catalog | null, language: Language) {
  return (catalog?.benchmarks.find(item => item.id === 'llm')?.providers || []).flatMap(provider =>
    provider.models.filter(model => model.name).flatMap(model => (model.credentials?.length ? model.credentials : [null]).map(credential => ({
      value: JSON.stringify({ id: provider.id, model: model.alias || model.name, credential_id: credential?.id || null }),
      label: `${providerDisplayName(provider.provider || provider.id, language, provider.label)} · ${model.alias || model.name}${credential ? ` · ${credential.name}` : ''}`,
    }))),
  );
}
export function selectionValue(selection: LlmSelection | null) {
  return selection ? JSON.stringify({ id: selection.id, model: selection.model, credential_id: selection.credential_id || null }) : '';
}
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
