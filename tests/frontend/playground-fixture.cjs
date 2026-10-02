// Isolated browser QA: synthetic responses only, no upstream requests or stored credentials.
// Build the frontend, then run: node tests/frontend/playground-fixture.cjs
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../frontend/dist');
const labels = { llm: 'LLM', embedding: 'Embedding', reranker: 'Reranker', audio: 'Audio', 'dify-chat': 'Dify Chat', 'dify-retrieve': 'Dify Retrieve' };
const parameters = {
  max_tokens: { type: 'integer', label: '最大输出 token 数', min: 1, max: 8192, default: 256 },
  temperature: { type: 'number', label: 'Temperature', min: 0, max: 2, step: 0.1, default: 1 },
  top_p: { type: 'number', label: 'Top P', min: 0, max: 1, step: 0.1, default: 1 },
  thinking: { type: 'enum', label: '深度思考', values: ['enabled', 'disabled'], default: 'enabled' },
  reasoning_effort: { type: 'enum', label: 'Reasoning effort', values: ['low', 'medium', 'high'], default: 'high', enabled_when: { thinking: 'enabled' } },
};
for (const spec of Object.values(parameters)) { spec.description = 'Local QA fixture'; spec.values ??= []; spec.enabled_when ??= {}; }
const catalog = { benchmarks: Object.entries(labels).map(([id, label]) => ({ id, label, provider_kinds: [], providers: [{ id: 'fixture', provider: 'fixture', label: 'Local QA fixture', icon: 'cube', endpoint_configured: true, dataset_id: 'fixture-dataset', credential_required: false, credential_configured: true, models: id.startsWith('dify-') ? [] : [{ name: 'fixture-model', alias: 'Fixture model', benchmark: id, credentials: [] }] }] })) };
function json(response, value, status = 200) { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(value)); }
http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/api/catalog') return json(response, catalog);
  if (url.pathname === '/api/llm/parameters') return json(response, { model: 'fixture-model', provider: 'fixture', version: 'fixture', model_specific: true, can_refresh: false, metadata: { context_window: 32768, max_output_tokens: 8192 }, parameters });
  if (url.pathname === '/api/playground/stream' || url.pathname === '/api/playground') {
    let body = '';
    for await (const chunk of request) body += chunk;
    const payload = JSON.parse(body);
    if (payload.query === '__error__') return json(response, { detail: 'Local fixture: credential rejected (HTTP 401)' }, 401);
    if (url.pathname === '/api/playground') return json(response, { ok: true, status_code: 200, duration_ms: 123.6, truncated: false, data: { fixture: true, benchmark: payload.benchmark } });
    response.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
    const answer = '这是本地模拟服务的回答，没有调用真实模型。\n\n左侧调整参数，右侧观察回答，底部输入新的测试问题。';
    const events = [
      { type: 'delta', channel: 'reasoning', content: '先理解问题，再组织一个简洁的回答。', ttft_ms: 120 },
      { type: 'delta', channel: 'content', content: answer.slice(0, 23), ttft_ms: 120 },
      { type: 'delta', channel: 'content', content: answer.slice(23), ttft_ms: 120 },
      { type: 'result', result: { ok: true, status_code: 200, duration_ms: 980, truncated: false, data: { content: answer, ttft_ms: 120, tpot_ms: 20, tokens_per_second: 50, output_tokens: 44 } } },
    ];
    let index = 0;
    response.write(JSON.stringify(events[index++]) + '\n');
    const timer = setInterval(() => {
      response.write(JSON.stringify(events[index++]) + '\n');
      if (index === events.length) { clearInterval(timer); response.end(); }
    }, payload.query === '__slow__' ? 5000 : 350);
    response.on('close', () => clearInterval(timer));
    return;
  }
  if (url.pathname.startsWith('/api/')) return json(response, []);
  const file = path.resolve(root, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { response.writeHead(404); return response.end(); }
  response.setHeader('Content-Type', { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(response);
}).listen(8082, '127.0.0.1', () => console.log('Synthetic Playground QA: http://127.0.0.1:8082/#playground'));
