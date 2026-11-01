import { useEffect, useState } from "react";
import type { PageResult } from "./pagination";

export function useServerPagination<Item>(fetchPage: (page: number, size: number, signal: AbortSignal) => Promise<PageResult<Item>>, enabled: boolean, revision: number) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [result, setResult] = useState<PageResult<Item> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
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
        const data = await fetchPage(page, pageSize, controller.signal);
        if (!controller.signal.aborted) { setResult(data); setPage(data.page); setError(""); }
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure));
      } finally {
        pending = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [fetchPage, enabled, revision, page, pageSize, retry]);
  const current = result?.page === page && result.page_size === pageSize;
  return {
    items: current ? result.items : [], total: result?.total ?? 0,
    page, pageSize, loading: loading || (!current && !error), error,
    onPageChange: (next: number) => { setError(""); setPage(next); },
    onPageSizeChange: (size: number) => { setError(""); setPage(1); setPageSize(size); },
    retry: () => setRetry(value => value + 1),
  };
}
