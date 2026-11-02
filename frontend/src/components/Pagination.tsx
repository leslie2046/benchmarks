import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import type { Language } from "../i18n";
import { clampPage, pageCount, pageItems } from "../pagination";

export function usePagination(total: number, resetKey = "") {
  const [state, setState] = useState({ page: 1, pageSize: 10, key: resetKey });
  const page = clampPage(state.key === resetKey ? state.page : 1, total, state.pageSize);
  useEffect(() => {
    if (state.page !== page || state.key !== resetKey) setState(current => ({ ...current, page, key: resetKey }));
  }, [page, resetKey, state.page, state.key]);
  return {
    page, pageSize: state.pageSize,
    onPageChange: (next: number) => setState(current => ({ ...current, page: next, key: resetKey })),
    onPageSizeChange: (next: number) => setState({ page: 1, pageSize: next, key: resetKey }),
  };
}

export function Pagination({ total, page, pageSize, onPageChange, onPageSizeChange, language, label, disabled = false }: {
  total: number; page: number; pageSize: number;
  onPageChange: (page: number) => void; onPageSizeChange: (size: number) => void;
  language: Language; label: string; disabled?: boolean;
}) {
  const chinese = language === "zh-CN";
  const pages = pageCount(total, pageSize);
  const start = total ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(page * pageSize, total);
  const pageOptions = [...new Set([1, ...Array.from({ length: 5 }, (_, index) => page + index - 2), pages])].filter(number => number >= 1 && number <= pages).sort((first, second) => first - second);
  return <nav className="pagination" aria-label={`${label} ${chinese ? "分页" : "pagination"}`}>
    <span className="pagination-summary" role="status">{chinese ? `第 ${start}–${end} 条，共 ${total} 条` : `${start}–${end} of ${total}`}</span>
    <div className="pagination-controls">
      <label><span>{chinese ? "每页" : "Rows"}</span><select aria-label={chinese ? "每页条数" : "Rows per page"} value={pageSize} disabled={disabled} onChange={event => onPageSizeChange(Number(event.target.value))}>{[10, 20, 50].map(size => <option key={size} value={size}>{size}</option>)}</select></label>
      <div className="pagination-navigation">
      <button type="button" disabled={disabled || page <= 1} onClick={() => onPageChange(1)} aria-label={chinese ? "首页" : "First page"} title={chinese ? "首页" : "First page"}><ChevronsLeft aria-hidden="true" /></button>
      <button type="button" disabled={disabled || page <= 1} onClick={() => onPageChange(page - 1)} aria-label={chinese ? "上一页" : "Previous page"}><ChevronLeft aria-hidden="true" /></button>
      <label className="pagination-page"><span className="sr-only">{chinese ? "页码" : "Page"}</span><select aria-label={chinese ? "页码" : "Page"} value={page} disabled={disabled || !total} onChange={event => onPageChange(Number(event.target.value))}>{pageOptions.map(number => <option key={number} value={number}>{number}</option>)}</select><span>/ {pages}</span></label>
      <button type="button" disabled={disabled || page >= pages} onClick={() => onPageChange(page + 1)} aria-label={chinese ? "下一页" : "Next page"}><ChevronRight aria-hidden="true" /></button>
      <button type="button" disabled={disabled || page >= pages} onClick={() => onPageChange(pages)} aria-label={chinese ? "末页" : "Last page"} title={chinese ? "末页" : "Last page"}><ChevronsRight aria-hidden="true" /></button>
      </div>
    </div>
  </nav>;
}

export function PaginatedList<Item>({ items, language, label, resetKey = "", children }: {
  items: Item[]; language: Language; label: string; resetKey?: string; children: (items: Item[]) => ReactNode;
}) {
  const pagination = usePagination(items.length, resetKey);
  return <>{children(pageItems(items, pagination.page, pagination.pageSize))}<Pagination {...pagination} total={items.length} language={language} label={label} /></>;
}
