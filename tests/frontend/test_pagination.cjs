const assert = require("node:assert/strict");
const path = require("node:path");
const { pageCount, clampPage, pageItems } = require(path.resolve(process.argv[2], "pagination.js"));

assert.equal(pageCount(0, 10), 1);
assert.equal(pageCount(11, 10), 2);
assert.equal(pageCount(20, 10), 2);
assert.equal(clampPage(9, 21, 10), 3);
assert.equal(clampPage(0, 21, 10), 1);
assert.equal(clampPage(2, 0, 10), 1);
const models = Array.from({ length: 86 }, (_, index) => ({ index, id: `model-${index}` }));
assert.deepEqual(pageItems(models, 2, 10).map(item => item.index), [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
assert.equal(pageItems(models, 9, 10).length, 6);
assert.equal(pageItems(models, 9, 50).length, 36);
assert.deepEqual(pageItems([], 9, 10), []);
const filtered = models.filter(item => item.index % 3 === 0);
assert.equal(pageItems(filtered, 2, 10)[0], models[30]);
assert.equal(models.length, 86);
console.log("Pagination checks passed: totals, bounds, empty/deleted pages, page sizes, filtered model indices.");
