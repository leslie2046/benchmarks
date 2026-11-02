import { Search } from "lucide-react";
import { tr, type Language } from "../i18n";

export function ListToolbar({ language, search, onSearch, searchLabel, filters, onReset }: {
  language: Language; search: string; onSearch: (value: string) => void; searchLabel: string;
  filters: Array<{ label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }> }>;
  onReset: () => void;
}) {
  const t = (value: string) => tr(language, value);
  const active = Boolean(search || filters.some(filter => filter.value));
  return <div className="list-toolbar" role="group" aria-label={t("搜索和筛选")}>
    <label className="list-search"><Search aria-hidden="true" /><input type="search" maxLength={200} value={search} onChange={event => onSearch(event.target.value)} aria-label={searchLabel} placeholder={searchLabel} /></label>
    {filters.map(filter => <label className="list-filter" key={filter.label}><span>{filter.label}</span><select aria-label={filter.label} value={filter.value} onChange={event => filter.onChange(event.target.value)}><option value="">{t("全部")}</option>{filter.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>)}
    {active && <button type="button" className="ghost" onClick={onReset}>{t("清除筛选")}</button>}
  </div>;
}
