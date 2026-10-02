const assert = require('node:assert/strict');
const path = require('node:path');
const { streamPlayground } = require(path.resolve(process.argv[2], 'api.js'));
const originalFetch = global.fetch;
const encode = value => new TextEncoder().encode(JSON.stringify(value) + '\n');
async function main() {
  const deltas = [];
  global.fetch = async () => new Response(new ReadableStream({ start(controller) {
    controller.enqueue(encode({type:'delta',content:'thinking',channel:'reasoning',ttft_ms:12}));
    controller.enqueue(encode({type:'delta',content:'answer',channel:'content',ttft_ms:12}));
    controller.enqueue(encode({type:'result',result:{ok:true,data:{content:'answer'}}}));
    controller.close();
  } }));
  const result = await streamPlayground({}, (...delta) => deltas.push(delta), new AbortController().signal);
  assert.equal(result.data.content, 'answer');
  assert.deepEqual(deltas.map(delta => delta[2]), ['reasoning','content']);
  let cancelled = 0;
  const abort = new AbortController();
  global.fetch = async () => new Response(new ReadableStream({ start(controller) {
    controller.enqueue(encode({type:'delta',content:'partial',channel:'content',ttft_ms:12}));
  }, cancel() { cancelled += 1; } }));
  await assert.rejects(streamPlayground({}, () => abort.abort(), abort.signal), error => error.name === 'AbortError');
  assert.equal(cancelled, 1, 'Cancellation must close the reader instead of waiting for more chunks');
  global.fetch = async () => new Response(JSON.stringify({detail:'Fixture error'}), {status:401});
  await assert.rejects(streamPlayground({}, () => {}, new AbortController().signal), /Fixture error/);
  global.fetch = async () => new Response('');
  await assert.rejects(streamPlayground({}, () => {}, new AbortController().signal), /ended before completion/);
  console.log('Playground streaming: success, channel separation, cancellation, HTTP error and incomplete-stream checks passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { global.fetch = originalFetch; });
