const assert = require("node:assert/strict");
const path = require("node:path");
const { memberPermissions, canManageTeams, restoredWorkspaceId } = require(path.resolve(process.argv[2], "workspacePermissions.js"));
const denied = { changeRole: false, remove: false };
for (const kind of ["team", "personal"]) for (const role of ["owner", "admin", "member"]) for (const targetRole of ["owner", "admin", "member"]) {
  const space = { id: "space", name: "Team", kind, role };
  const target = { id: "other", username: "other", name: "Other", provider: "github", role: targetRole };
  const result = memberPermissions(space, "self", target);
  if (kind === "personal" || role === "member" || targetRole === "owner") assert.deepEqual(result, denied);
  else if (role === "owner") assert.deepEqual(result, {changeRole: true, remove: true});
  else assert.deepEqual(result, {changeRole: false, remove: targetRole === "member"});
  assert.deepEqual(memberPermissions(space, "other", target), denied);
}
for (const kind of ["personal", "team"]) for (const role of ["owner", "admin", "member"]) {
  assert.equal(canManageTeams({id:"space", name:"Space", kind, role}), kind === "team" && role === "owner");
}
assert.equal(canManageTeams(null),false);
const spaces=[{id:"personal",kind:"personal",role:"owner"},{id:"team",kind:"team",role:"member"}];
assert.equal(restoredWorkspaceId(spaces,"team","session","session"),"team");
assert.equal(restoredWorkspaceId(spaces,"team","old-session","new-session"),null);
assert.equal(restoredWorkspaceId(spaces,"team",null,"session"),null);
assert.equal(restoredWorkspaceId(spaces,"team",null,null),null);
assert.equal(restoredWorkspaceId(spaces,"removed","session","session"),null);
assert.equal(restoredWorkspaceId([],"team","session","session"),null);
console.log("Workspace member permissions passed: all roles, owner protection, personal spaces and self-action restrictions.");
