import { ChevronRight, Users } from "lucide-react";
import { useAuth } from "../auth";
import { tr, type Language } from "../i18n";
import { Dropdown } from "./Dropdown";

export function WorkspaceControls({ language, onSettings, onClose }: {
  language: Language; onSettings: (section: "members") => void; onClose: () => void;
}) {
  const auth = useAuth();
  const t = (value: string) => tr(language, value);
  if (!auth.user || !auth.workspace || !auth.canManageTeams) return null;
  return <div className="workspace-controls">
    <Dropdown label={t("团队管理")} className="identity-menu-item workspace-menu-trigger" side="right" trigger={<><Users aria-hidden="true" /><span>{t("团队管理")}</span><ChevronRight aria-hidden="true" /></>}>
      {close => <>
        <button type="button" className="identity-menu-item" onClick={() => { close(); onClose(); onSettings("members"); }}><Users aria-hidden="true" />{t("成员管理")}</button>
      </>}
    </Dropdown>
  </div>;
}
