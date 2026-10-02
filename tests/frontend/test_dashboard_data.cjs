const assert = require('node:assert/strict');
const path = require('node:path');
const { modelKey, metricValue, hasTrend, validTrendRuns } = require(path.resolve(process.argv[2], 'dashboardData.js'));

function scenario(model, concurrency = 1, success = 10) {
  return { provider: 'fixture', provider_name: 'Fixture', model, concurrency,
    result: { success_count: success, failure_count: 0, qps_success: 5,
      metrics: { latency_ms: { p50: 20, p95: 30, p99: 40 }, ttft_ms: { avg: 10 } } } };
}
const a = scenario('a');
const b = scenario('b');
const run = (id, scenarios) => ({ id, created_at: '2026-10-02T03:11:00Z', scenarios });
assert.notEqual(modelKey(a), modelKey(b), 'Models from the same provider must not collapse into one series');
assert.equal(modelKey(a), modelKey(scenario('a', 20)), 'Concurrency is an axis, not part of the model identity');
assert.equal(hasTrend([run('1', [a])], 1, 'p95'), false, 'One run is not a trend');
assert.equal(hasTrend([run('1', [a]), run('2', [b])], 1, 'p95'), false, 'Different models do not establish a trend');
assert.equal(hasTrend([run('1', [a]), run('2', [scenario('a', 5)])], 1, 'p95'), false, 'Different levels must not be mixed');
assert.equal(hasTrend([run('1', [a, a])], 1, 'p95'), false, 'Duplicate scenarios within a run count once');
assert.equal(hasTrend([run('1', [a]), run('2', [a])], 1, 'p95'), true, 'Distinct runs at identical timestamps remain distinct');
assert.equal(validTrendRuns([run('1', [a]), run('2', [scenario('a', 1, 0)])], 1, 'p95').length, 1);
assert.equal(metricValue(scenario('a', 1, 0), 'p95'), null);
assert.equal(metricValue(a, 'tpot'), null, 'Missing LLM metrics are not zero');
assert.equal(metricValue({ ...a, result: { ...a.result, qps_success: NaN } }, 'qps'), null);
assert.equal(metricValue(a, 'error'), 0, 'A valid zero failure rate remains drawable');
console.log('12 dashboard data checks passed');
