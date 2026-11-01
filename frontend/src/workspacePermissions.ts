import type { Workspace } from "./auth";
import type { WorkspaceMember } from "./api";

export function memberPermissions(workspace: Workspace, userId: string, member: WorkspaceMember) {
  const otherMember = workspace.kind === "team" && member.id !== userId && member.role !== "owner";
  const owner = workspace.role === "owner";
  return {
    changeRole: otherMember && owner,
    remove: otherMember && (owner || (workspace.role === "admin" && member.role === "member")),
  };
}

export function canManageTeams(workspace: Workspace | null) {
  return workspace?.kind === "team" && workspace.role === "owner";
}

export function restoredWorkspaceId(workspaces: Workspace[], savedId: string | null, savedSession: string | null, currentSession: string | null) {
  return currentSession && savedSession === currentSession && workspaces.some(workspace => workspace.id === savedId) ? savedId : null;
}
