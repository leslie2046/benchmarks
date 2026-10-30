const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const outputDirectory = path.resolve(process.argv[2]);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function loadModule(filename, cryptoApi) {
  const sandbox = {
    exports: {},
    crypto: cryptoApi,
    require(name) {
      if (name === "../clientId") return loadModule("clientId.js", cryptoApi);
      return {};
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(outputDirectory, filename), "utf8"), sandbox, { filename });
  return sandbox.exports;
}

function createFactory(cryptoApi) {
  return loadModule("components/DocumentListEditor.js", cryptoApi).createDocumentDraft;
}

const nativeId = "12345678-1234-4123-8123-123456789abc";
const nativeCrypto = {
  randomUUID() {
    assert.equal(this, nativeCrypto);
    return nativeId;
  },
};
const createNativeDraft = createFactory(nativeCrypto);
assert.equal(createNativeDraft().id, nativeId);
assert.equal(createNativeDraft().text, "");
assert.equal(createNativeDraft("candidate document").text, "candidate document");

for (const [fill, expected] of [
  [0, "00000000-0000-4000-8000-000000000000"],
  [255, "ffffffff-ffff-4fff-bfff-ffffffffffff"],
]) {
  const createHttpDraft = createFactory({
    getRandomValues(bytes) {
      assert.equal(bytes.length, 16);
      return bytes.fill(fill);
    },
  });
  const draft = createHttpDraft("HTTP document");
  assert.equal(draft.id, expected);
  assert.equal(draft.text, "HTTP document");
}

const createHttpDraft = createFactory({
  getRandomValues(bytes) {
    return webcrypto.getRandomValues(bytes);
  },
});
const ids = Array.from({ length: 1000 }, () => createHttpDraft().id);
assert.equal(new Set(ids).size, ids.length);
assert.ok(ids.every(id => uuidPattern.test(id)));
console.log("Document drafts: native UUID, HTTP fallback, UUID format and unique IDs passed");
