const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { providerPresets } = require(path.resolve(process.argv[2], 'providerPresets.js'));

for (const [provider, preset] of Object.entries(providerPresets)) {
  assert(preset.logoUrl.startsWith('/provider-logos/'), `${provider} must have a local logo`);
  const asset = path.resolve(__dirname, '../../frontend/public', preset.logoUrl.slice(1));
  assert(fs.statSync(asset).size > 0, `${provider} logo must exist`);
  if (asset.endsWith('.svg')) {
    const svg = fs.readFileSync(asset, 'utf8');
    assert(svg.startsWith('<svg'));
    assert(!/<script|\bon\w+\s*=|(?:href|src)\s*=/i.test(svg), `${provider} SVG must not execute code or fetch external resources`);
  }
}

const officialHosts = {
  moonshot: 'platform.kimi.com',
  qwen: 'platform.qianwenai.com',
  minimax: 'platform.minimax.cn',
  volcengine: 'console.volcengine.com',
  deepseek: 'platform.deepseek.com',
  siliconflow: 'cloud.siliconflow.cn',
  aliyun: 'bailian.console.aliyun.com',
  xunfei: 'maas.xfyun.cn',
  huaweiyun: 'console.huaweicloud.com',
};
for (const [provider, hostname] of Object.entries(officialHosts)) {
  const url = new URL(providerPresets[provider].apiKeyUrl);
  assert.equal(url.protocol, 'https:');
  assert.equal(url.hostname, hostname);
  assert.equal(url.username, '');
  assert.equal(url.password, '');
  assert.equal(url.search, '');
  assert.equal(url.hash, '');
}
for (const provider of ['xinference', 'vllm']) {
  assert.equal(providerPresets[provider].apiKeyUrl, undefined, 'Self-hosted providers have no central API key portal');
}
for (const provider of ['moonshot', 'qwen', 'minimax', 'volcengine']) {
  assert.equal(new URL(providerPresets[provider].serverUrl).protocol, 'https:');
  assert.equal(providerPresets[provider].apiKeyRequired, true);
}
console.log('Provider key links passed: official HTTPS hosts, no credentials or query data, no self-hosted portal.');
assert.equal(providerPresets.qwen.apiKeyUrl, 'https://platform.qianwenai.com/home/api-keys');
assert.equal(providerPresets.qwen.logoUrl, '/provider-logos/qianwen.svg');
assert.equal(providerPresets.qwen.serverUrl, 'https://maas.qianwenaiapi.com/compatible-mode/v1');
assert.equal(providerPresets.aliyun.serverUrl, 'https://dashscope.aliyuncs.com/compatible-mode');
