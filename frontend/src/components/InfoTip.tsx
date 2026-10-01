import { useId } from "react";
import { Info } from "lucide-react";

export function InfoTip({ text, label = "More information" }: { text: string; label?: string }) {
  const id = useId();
  return <span className="info-tip" tabIndex={0} aria-label={label} aria-describedby={id}>
    <Info aria-hidden="true" />
    <span className="info-tip-content" id={id} role="tooltip">{text}</span>
  </span>;
}
