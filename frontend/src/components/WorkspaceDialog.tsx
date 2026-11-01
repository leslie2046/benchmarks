import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { tr, type Language } from "../i18n";

export function WorkspaceDialog({ title, busy, language, onClose, children }: {
  title: string; busy: boolean; language: Language; onClose: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    element?.querySelector<HTMLInputElement>("input")?.focus();
    return () => { if (element?.open) element.close(); };
  }, []);
  return <dialog ref={dialog} className="workspace-dialog" aria-label={title} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="workspace-dialog-head"><h2>{title}</h2><button type="button" className="icon-button" aria-label={tr(language, "关闭")} disabled={busy} onClick={onClose}><X aria-hidden="true" /></button></header>
    {children}
  </dialog>;
}
