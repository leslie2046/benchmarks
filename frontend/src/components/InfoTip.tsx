import { useId, useState } from "react";
import { Info } from "lucide-react";

export function InfoTip({ text, label = "More information" }: { text: string; label?: string }) {
  const id = useId();
  const [position, setPosition] = useState({ left: 0, top: 0 });
  function place(target: HTMLElement) {
    const anchor = target.getBoundingClientRect();
    const tooltip = target.querySelector<HTMLElement>(".info-tip-content")?.getBoundingClientRect();
    const width = tooltip?.width ?? 280;
    const height = tooltip?.height ?? 80;
    setPosition({ left: Math.max(8, Math.min(anchor.left - 8, window.innerWidth - width - 8)),
      top: anchor.bottom + height + 7 < window.innerHeight ? anchor.bottom + 7 : Math.max(8, anchor.top - height - 7) });
  }
  return <span className="info-tip" tabIndex={0} aria-label={label} aria-describedby={id} onMouseEnter={(event) => place(event.currentTarget)} onFocus={(event) => place(event.currentTarget)}>
    <Info aria-hidden="true" />
    <span className="info-tip-content" style={position} id={id} role="tooltip">{text}</span>
  </span>;
}
