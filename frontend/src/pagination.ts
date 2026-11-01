export type PageResult<Item> = { items: Item[]; total: number; page: number; page_size: number };

export function pageCount(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / pageSize));
}

export function clampPage(page: number, total: number, pageSize: number) {
  return Math.max(1, Math.min(page, pageCount(total, pageSize)));
}

export function pageItems<Item>(items: Item[], page: number, pageSize: number) {
  const start = (clampPage(page, items.length, pageSize) - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
