import { useEffect, useState } from "react";
import { Boxes } from "lucide-react";
import { providerPresets } from "../providerPresets";

export function ProviderLogo({ providerId }: { providerId: string }) {
  const logoUrl = providerPresets[providerId]?.logoUrl;
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [logoUrl]);

  return <span className="provider-logo" aria-hidden="true">
    {logoUrl && !failed
      ? <img src={logoUrl} alt="" width="20" height="20" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
      : <Boxes />}
  </span>;
}
