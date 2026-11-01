import { useLayoutEffect, useId, useRef, useState, type ReactNode } from "react";

export function Dropdown({ label, trigger, children, className = "", side = "bottom", width = 280, disabled = false }: {
  label: string; trigger: ReactNode; children: (close: () => void) => ReactNode;
  className?: string; side?: "top" | "bottom" | "right"; width?: number; disabled?: boolean;
}) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, width });
  const close = () => popup.current?.hidePopover();
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const bounds = button.current?.getBoundingClientRect();
      if (!bounds) return;
      const popupWidth = Math.min(width, window.innerWidth - 24);
      const height = Math.min(popup.current?.offsetHeight || 320, window.innerHeight - 24);
      if (side === "right") {
        const right = bounds.right + 6;
        const left = right + popupWidth <= window.innerWidth - 12 ? right : Math.max(12, bounds.left - popupWidth - 6);
        setPosition({ left, top: Math.max(12, Math.min(bounds.top, window.innerHeight - height - 12)), width: popupWidth });
        return;
      }
      const below = bounds.bottom + 6;
      const top = side === "top" || below + height > window.innerHeight - 12 ? Math.max(12, bounds.top - height - 6) : below;
      setPosition({ left: Math.max(12, Math.min(bounds.left, window.innerWidth - popupWidth - 12)), top, width: popupWidth });
    };
    place();
    popup.current?.querySelector<HTMLElement>("button:not(:disabled), input, select")?.focus();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, width, side]);
  return <>
    <button type="button" className={className} ref={button} aria-label={label} aria-haspopup="dialog" aria-expanded={open} aria-controls={id} disabled={disabled} onClick={() => popup.current?.togglePopover()}>{trigger}</button>
    <div id={id} ref={popup} popover="auto" className="identity-popover" role="dialog" aria-label={label} style={position} onToggle={() => setOpen(popup.current?.matches(":popover-open") ?? false)} onKeyDown={event => {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation(); close(); button.current?.focus(); return;
      }
      if (!(event.target instanceof HTMLButtonElement) || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const controls = [...(popup.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])].filter(control => control.closest("[popover]") === popup.current);
      const current = controls.indexOf(event.target);
      const next = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + controls.length) % controls.length;
      event.preventDefault(); event.stopPropagation(); controls[next]?.focus();
    }}>{children(close)}</div>
  </>;
}

export function IdentityAvatar({ name, workspace = false, src }: { name: string; workspace?: boolean; src?: string | null }) {
  const [failed, setFailed] = useState<string | null>(null);
  return <span className={`identity-avatar${workspace ? " workspace-avatar" : ""}`} aria-hidden="true">{src && src !== failed ? <img src={src} alt="" onError={() => setFailed(src)} /> : [...name.trim()][0]?.toLocaleUpperCase() || "P"}</span>;
}
