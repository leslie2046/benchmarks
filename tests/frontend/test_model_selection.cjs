const assert = require("node:assert/strict");
const path = require("node:path");
const { updateModelSelection } = require(path.resolve(process.argv[2], "modelSelection.js"));
const original = { llm: true, embedding: false, rerank: false, existing: false, unknown: false };
const eligible = new Set(["llm", "embedding", "rerank"]);
assert.deepEqual(updateModelSelection(original, Object.keys(original), eligible, true),
  { llm: true, embedding: true, rerank: true, existing: false, unknown: false });
assert.deepEqual(updateModelSelection(original, ["embedding", "rerank"], eligible, true),
  { ...original, embedding: true, rerank: true });
assert.deepEqual(updateModelSelection({ ...original, embedding: true }, ["embedding"], eligible, false), original);
assert.deepEqual(updateModelSelection(original, Object.keys(original), eligible, false),
  Object.fromEntries(Object.keys(original).map(id => [id, false])));
assert.equal(original.llm, true);
assert.equal(original.embedding, false);
assert.deepEqual(updateModelSelection(original, [], eligible, true), original);
console.log("Model selection tests passed");
