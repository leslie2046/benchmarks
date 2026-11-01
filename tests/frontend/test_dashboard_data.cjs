const assert = require('node:assert/strict');
const path = require('node:path');
const { modelKey, metricValue, hasTrend, validTrendRuns, trendSeries } = require(path.resolve(process.argv[2], 'dashboardData.js'));

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
const mixedRuns = [run('1', [a, scenario('a', 5), b]), run('2', [a, scenario('a', 20), b]), run('3', [scenario('a', 5)])];
const combined = trendSeries(mixedRuns, undefined, 'p95');
assert.deepEqual(combined.map(item => [item.model.model, item.concurrency, item.data]), [
  ['a', 1, [30, 30, null]], ['a', 5, [30, null, 30]], ['a', 20, [null, 30, null]], ['b', 1, [30, 30, null]],
], 'All levels remain separate model/level series with aligned run gaps, not averaged');
assert.equal(hasTrend(mixedRuns, undefined, 'p95'), true);
assert.equal(hasTrend([run('1', [a]), run('2', [scenario('a', 5)])], undefined, 'p95'), false, 'Different levels alone cannot establish an all-level trend');
assert.equal(hasTrend([run('1', [a, a])], undefined, 'p95'), false, 'Duplicates in one run are not multiple runs');
assert.deepEqual(trendSeries(mixedRuns, 5, 'p95').map(item => item.data), [[30, null, 30]], 'Single-level filtering is preserved');
assert.equal(validTrendRuns(mixedRuns, undefined, 'p95').length, 3);
assert.deepEqual(trendSeries([], undefined, 'p95'), []);
assert.deepEqual(trendSeries([run('1', [scenario('a', 1, 0)]), run('2', [a])], undefined, 'p95')[0].data, [null, 30]);
assert.deepEqual(trendSeries([run('1', [scenario('a', 1, 0)]), run('2', [a])], undefined, 'error')[0].data, [null, 0], 'No requests is missing, valid zero error remains zero');
console.log('21 dashboard data checks passed');
