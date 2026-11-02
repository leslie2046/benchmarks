import { useEffect, useState } from "react";
import type { PageResult } from "./pagination";
import type { ListFilters } from "./api";

export function useServerPagination<Item>(fetchPage: (page: number, size: number, signal: AbortSignal, filters: ListFilters) => Promise<PageResult<Item>>, enabled: boolean, revision: number, filters: ListFilters = {}) {
  const [search, setSearch] = useState(filters.q || "");
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch((filters.q || "").trim()), 250);
    return () => window.clearTimeout(timer);
  }, [filters.q]);
  const key = JSON.stringify({ q: search, status: filters.status || "", benchmark: filters.benchmark || "", repeat_mode: filters.repeat_mode || "" });
  const [position, setPosition] = useState({ page: 1, pageSize: 10, key });
  const page = position.key === key ? position.page : 1;
  const pageSize = position.pageSize;
  useEffect(() => {
    setPosition(current => current.key === key ? current : { ...current, key, page: 1 });
  }, [key]);
  const [result, setResult] = useState<{ key: string; data: PageResult<Item> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState({ key: "", message: "" });
  const error = failure.key === key ? failure.message : "";
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      setLoading(true);
      try {
        const data = await fetchPage(page, pageSize, controller.signal, JSON.parse(key) as ListFilters);
        if (!controller.signal.aborted) {
          setResult({ key, data }); setPosition({ page: data.page, pageSize, key }); setFailure({ key, message: "" });
        }
      } catch (reason) {
        if (!controller.signal.aborted) setFailure({ key, message: reason instanceof Error ? reason.message : String(reason) });
      } finally {
        pending = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [fetchPage, enabled, revision, page, pageSize, key, retry]);
  const current = result?.key === key && result.data.page === page && result.data.page_size === pageSize;
  return {
    items: current ? result.data.items : [], total: result?.key === key ? result.data.total : 0,
    page, pageSize, loading: loading || (!current && !error), error,
    onPageChange: (next: number) => { setFailure({ key, message: "" }); setPosition({ page: next, pageSize, key }); },
    onPageSizeChange: (size: number) => { setFailure({ key, message: "" }); setPosition({ page: 1, pageSize: size, key }); },
    retry: () => setRetry(value => value + 1),
  };
}
