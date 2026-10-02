"""Read-only Dify application and knowledge base name discovery."""
import requests
from urllib.parse import quote


def api_root(url):
    root = url.rstrip('/')
    return root if root.endswith('/v1') else root + '/v1'


def fetch_names(server_url, benchmark, api_key, page=1, dataset_id=None):
    if not api_key:
        raise ValueError('请填写对应的 API Key，或使用已保存的密钥。')
    endpoint = api_root(server_url) + ('/info' if benchmark == 'dify-chat' else '/datasets')
    if benchmark == 'dify-retrieve' and dataset_id:
        endpoint += '/' + quote(dataset_id.strip(), safe='')
    try:
        response = requests.get(endpoint, headers={'Authorization': f'Bearer {api_key}'},
                                params={'page': page, 'limit': 100} if benchmark == 'dify-retrieve' and not dataset_id else None,
                                timeout=(3, 12), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError('无法连接 Dify，请检查服务地址和网络。') from exc
    if response.status_code in {401, 403}:
        raise ValueError('Dify 拒绝访问，请检查 API Key 是否有效且与当前类型匹配。')
    if not 200 <= response.status_code < 300:
        raise ValueError(f'获取名称失败（HTTP {response.status_code}），请检查 Dify API 地址及版本。')
    try:
        body = response.json()
    except ValueError as exc:
        raise ValueError('Dify 未返回有效 JSON，请检查服务地址。') from exc
    if not isinstance(body, dict):
        raise ValueError('Dify 名称响应格式不正确。')
    entries = [body] if benchmark == 'dify-chat' or dataset_id else body.get('data')
    if not isinstance(entries, list):
        raise ValueError('Dify 未返回知识库列表。')
    names = []
    for entry in entries[:100]:
        if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name'].strip():
            identifier = entry.get('id') if benchmark == 'dify-retrieve' else 'app'
            if isinstance(identifier, str):
                names.append({'id': identifier, 'name': entry['name'].strip()})
    if dataset_id and not names:
        raise ValueError('Dify 未返回知识库名称，请检查知识库 ID 和权限。')
    if benchmark == 'dify-chat' and not names:
        raise ValueError('Dify 未返回应用名称，请确认应用已发布且版本支持 /info。')
    return {'names': names, 'has_more': bool(body.get('has_more')) if benchmark == 'dify-retrieve' and not dataset_id else False, 'page': page}
