import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { authenticatedFetch, setCsrfToken, setWorkspaceId } from "./api";
import { LoginPage } from "./components/LoginPage";
import { WorkspaceSelection } from "./components/WorkspaceSelection";
import { canManageTeams, restoredWorkspaceId } from "./workspacePermissions";

import type { AuthUser } from "./types";
export type { AuthUser } from "./types";
export type Workspace = { id: string; name: string; kind: "personal" | "team"; role: "owner" | "admin" | "member" };
export type AuthStatus = {
  enabled: boolean;
  password_enabled: boolean;
  csrf_token: string | null;
  user: AuthUser | null;
  providers: { id: string; name: string; enabled: boolean; login_url: string }[];
  workspaces?: Workspace[];
  personal_workspace_id?: string;
};

const AuthContext = createContext<{
  user: AuthUser | null; logout: () => Promise<void>; workspace: Workspace | null;
  workspaces: Workspace[]; canManage: boolean; switchWorkspace: (id: string) => void;
  refreshWorkspaces: (preferredId?: string) => Promise<void>;
  canManageTeams: boolean; chooseWorkspace: () => void;
  updateUser: (user: AuthUser) => void;
}>({ user: null, logout: async () => {}, workspace: null, workspaces: [], canManage: true, canManageTeams: false, switchWorkspace: () => {}, refreshWorkspaces: async () => {}, chooseWorkspace: () => {}, updateUser: () => {} });

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const revision = useRef(0);
  const apply = useCallback((value: AuthStatus) => {
    revision.current += 1;
    setLoading(false);
    setError(false);
    setCsrfToken(value.csrf_token);
    setStatus(value);
    const savedId = value.user ? sessionStorage.getItem(`prismlab-workspace:${value.user.id}`) : null;
    const savedSession = value.user ? sessionStorage.getItem(`prismlab-workspace-session:${value.user.id}`) : null;
    const nextId = restoredWorkspaceId(value.workspaces ?? [], savedId, savedSession, value.csrf_token);
    setSelectedId(nextId);
    setWorkspaceId(nextId);
    if (value.enabled && !value.user && window.location.pathname !== "/login") {
      window.history.replaceState(null, "", `/login${window.location.search}${window.location.hash}`);
    } else if ((!value.enabled || value.user) && window.location.pathname === "/login") {
      window.history.replaceState(null, "", `/${window.location.hash}`);
    }
  }, []);
  const refresh = useCallback(async () => {
    const requestRevision = ++revision.current;
    setLoading(true);
    setError(false);
    try {
      const response = await fetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Authentication service unavailable");
      const value = await response.json() as AuthStatus;
      if (revision.current === requestRevision) apply(value);
    } catch {
      if (revision.current === requestRevision) { setError(true); setLoading(false); }
    }
  }, [apply]);

  useEffect(() => {
    void refresh();
    const expired = () => {
      setCsrfToken(null);
      setWorkspaceId(null);
      setSelectedId(null);
      setStatus(null);
      void refresh();
    };
    window.addEventListener("prismlab:unauthorized", expired);
    window.addEventListener("prismlab:workspaces-changed", expired);
    return () => {
      window.removeEventListener("prismlab:unauthorized", expired);
      window.removeEventListener("prismlab:workspaces-changed", expired);
    };
  }, [refresh]);

  async function logout() {
    const response = await authenticatedFetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) throw new Error("Logout failed");
    if (status?.user) {
      sessionStorage.removeItem(`prismlab-workspace:${status.user.id}`);
      sessionStorage.removeItem(`prismlab-workspace-session:${status.user.id}`);
    }
    if (status) apply({ ...status, user: null, csrf_token: null, workspaces: [], personal_workspace_id: undefined });
  }

  function switchWorkspace(id: string) {
    if (!status?.user || !status.workspaces?.some(workspace => workspace.id === id)) return;
    sessionStorage.setItem(`prismlab-workspace:${status.user.id}`, id);
    if (status.csrf_token) sessionStorage.setItem(`prismlab-workspace-session:${status.user.id}`, status.csrf_token);
    setWorkspaceId(id);
    setSelectedId(id);
  }

  async function refreshWorkspaces(preferredId?: string) {
    const response = await fetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Unable to refresh workspaces");
    const value = await response.json() as AuthStatus;
    if (preferredId && value.user && value.workspaces?.some(workspace => workspace.id === preferredId)) {
      sessionStorage.setItem(`prismlab-workspace:${value.user.id}`, preferredId);
      if (value.csrf_token) sessionStorage.setItem(`prismlab-workspace-session:${value.user.id}`, value.csrf_token);
    }
    apply(value);
  }

  if (loading || error || !status || (status.enabled && !status.user)) {
    return <LoginPage status={status} loading={loading} unavailable={error} onRetry={() => void refresh()} onLogin={apply} />;
  }
  const workspace = status.workspaces?.find(item => item.id === selectedId) ?? null;
  if (status.enabled && status.user && !workspace) {
    return <WorkspaceSelection user={status.user} workspaces={status.workspaces ?? []} onSelect={switchWorkspace} onLogout={logout} onRefresh={() => refreshWorkspaces()} onCreated={id => refreshWorkspaces(id)} />;
  }
  return <AuthContext.Provider key={workspace?.id ?? "legacy"} value={{ user: status.user, logout, workspace,
    workspaces: status.workspaces ?? [], canManage: !workspace || workspace.role !== "member", switchWorkspace, refreshWorkspaces,
    updateUser: user => setStatus(current => current?.user?.id === user.id ? { ...current, user } : current),
    canManageTeams: canManageTeams(workspace), chooseWorkspace: () => {
      if (status.user) sessionStorage.removeItem(`prismlab-workspace:${status.user.id}`);
      setWorkspaceId(null); setSelectedId(null);
    } }}>{children}</AuthContext.Provider>;
}
