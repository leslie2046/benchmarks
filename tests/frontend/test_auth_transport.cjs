const assert = require('node:assert/strict');
const path = require('node:path');
const { authenticatedFetch, setCsrfToken, setWorkspaceId, subscribeToRun, profileApi } = require(path.resolve(process.argv[2], 'api.js'));
const originalFetch = global.fetch;
const originalWindow = global.window;

async function main() {
  const calls = [];
  global.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response('{}');
  };
  setCsrfToken('session-csrf-token');
  setWorkspaceId('team-one');
  await authenticatedFetch('/api/private', { method: 'post', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  assert.equal(calls[0].init.headers.get('X-CSRF-Token'), 'session-csrf-token');
  assert.equal(calls[0].init.headers.get('Content-Type'), 'application/json');
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.equal(calls[0].init.headers.get('X-Workspace-Id'), 'team-one');
  await authenticatedFetch('/api/private');
  assert.equal(calls[1].init.headers.has('X-CSRF-Token'), false);
  setWorkspaceId('personal-two');
  setCsrfToken(null);
  await authenticatedFetch('/api/private', { method: 'DELETE' });
  assert.equal(calls[2].init.headers.has('X-CSRF-Token'), false);
  assert.equal(calls[2].init.headers.get('X-Workspace-Id'), 'personal-two');
  assert.equal(calls[0].init.headers.get('X-Workspace-Id'), 'team-one');
  setCsrfToken('profile-csrf');
  await profileApi.nickname('New nickname');
  assert.equal(calls[3].url, '/api/auth/profile');
  assert.equal(calls[3].init.method, 'PATCH');
  assert.deepEqual(JSON.parse(calls[3].init.body), {nickname: 'New nickname'});
  assert.equal(calls[3].init.headers.get('X-CSRF-Token'), 'profile-csrf');
  const image = new Blob(['fixture-image'], {type: 'image/png'});
  await profileApi.avatar(image);
  assert.equal(calls[4].url, '/api/auth/profile/avatar');
  assert.equal(calls[4].init.method, 'PUT');
  assert.equal(calls[4].init.headers.get('Content-Type'), 'image/png');
  assert.equal(calls[4].init.body, image);
  assert.equal(calls[4].init.headers.get('X-CSRF-Token'), 'profile-csrf');
  await profileApi.removeAvatar();
  assert.equal(calls[5].init.method, 'DELETE');
  global.window = new EventTarget();
  let expired = 0;
  window.addEventListener('prismlab:unauthorized', () => { expired += 1; });
  global.fetch = async () => new Response('{}', { status: 401 });
  const response = await authenticatedFetch('/api/private');
  assert.equal(response.status, 401);
  assert.equal(expired, 1);
  let changed = 0;
  window.addEventListener('prismlab:workspaces-changed', () => { changed += 1; });
  global.fetch = async () => new Response(JSON.stringify({ detail: { code: 'workspace_unavailable' } }), { status: 403 });
  await authenticatedFetch('/api/private');
  assert.equal(changed, 1);
  const previousEventSource = global.EventSource;
  let sourceUrl;
  global.EventSource = class { constructor(url) { sourceUrl = url; } close() {} };
  try {
    subscribeToRun('abcdef', () => {}, () => {})();
    assert.equal(sourceUrl, '/api/runs/abcdef/events?workspace_id=personal-two');
  } finally {
    if (previousEventSource === undefined) delete global.EventSource;
    else global.EventSource = previousEventSource;
  }
  console.log('Authentication transport: CSRF, credentials, token clearing and session expiry checks passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  global.fetch = originalFetch;
  if (originalWindow === undefined) delete global.window;
  else global.window = originalWindow;
  setCsrfToken(null);
  setWorkspaceId(null);
});
