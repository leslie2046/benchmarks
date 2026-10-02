/** Apply a bulk operation without changing selections outside its scope. */
export function updateModelSelection(
  selected: Record<string, boolean>,
  scopeIds: string[],
  eligibleIds: Set<string>,
  checked: boolean,
): Record<string, boolean> {
  const next = { ...selected };
  for (const id of scopeIds) next[id] = checked && eligibleIds.has(id);
  return next;
}
