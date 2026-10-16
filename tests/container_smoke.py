"""Prepare isolated media, or check a running Docker/Podman deployment.

python tests/container_smoke.py prepare .test-data/container-smoke/media
QMAXHUB_TEST_PASSWORD=... python tests/container_smoke.py check http://127.0.0.1:18097
The check expects only the fictional SMOKE-001 fixture in the test library.
"""
import argparse
import base64
import http.client
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
TARGET = 'https://example.test/container-smoke.mp4?token=a%2Fb&source=test'


def prepare(directory):
    folder = Path(directory) / 'SMOKE-001'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'SMOKE-001-CD1.strm').write_text(TARGET, encoding='utf-8')
    (folder / 'SMOKE-001-CD2.strm').write_text('https://example.test/container-smoke-part2.mp4', encoding='utf-8')
    (folder / 'SMOKE-001.nfo').write_text('''<movie><num>SMOKE-001</num>
<title>容器测试 &amp; 本地元数据</title><plot>虚构资料，仅用于容器验证。</plot>
<actor><name>测试演员</name></actor><tag>容器测试</tag><studio>测试工作室</studio>
<runtime>120</runtime><premiered>2026-10-16</premiered></movie>''', encoding='utf-8')
    (folder / 'poster.png').write_bytes(PNG)
    (folder / 'extrafanart').mkdir(exist_ok=True)
    (folder / 'extrafanart' / '1.png').write_bytes(PNG)
    print('Prepared fictional SMOKE-001 media:', Path(directory).resolve())


def check(base, expect_persisted=False):
    server = urlsplit(base)
    if server.scheme not in ('http', 'https') or not server.hostname:
        raise ValueError('Expected an HTTP(S) URL')
    password = os.environ['QMAXHUB_TEST_PASSWORD']
    cookie = ''

    def request(path, body=None, extra=None, method=None):
        connection_class = http.client.HTTPSConnection if server.scheme == 'https' else http.client.HTTPConnection
        conn = connection_class(server.hostname, server.port, timeout=10)
        headers = {'Cookie': cookie, **(extra or {})}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        conn.request(method or ('POST' if body is not None else 'GET'), path, payload, headers)
        response = conn.getresponse()
        data, status, received = response.read(), response.status, dict(response.getheaders())
        content_type = response.getheader('Content-Type', '')
        conn.close()
        return status, received, json.loads(data) if data and 'application/json' in content_type else data

    def require(condition, message):
        if not condition:
            raise AssertionError(message)
        print('PASS', message, flush=True)

    deadline = time.monotonic() + 60
    while True:
        try:
            ready = request('/health')[0] == 200
        except OSError:
            ready = False
        if ready:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Container did not become ready within 60 seconds')
        time.sleep(1)
    require(ready, 'health endpoint')
    require(request('/')[0] == 200, 'web UI served')
    require(request('/api/movies')[0] == 401, 'anonymous library access rejected')
    status, headers, _ = request('/api/login', {'password': password})
    require(status == 200, 'administrator login')
    cookie = headers['Set-Cookie'].split(';')[0]
    status, _, scan = request('/api/scan', {})
    require(status == 202, 'manual scan accepted')
    while scan['running']:
        if time.monotonic() >= deadline:
            raise TimeoutError('Container scan did not complete')
        time.sleep(.2)
        scan = request('/api/scan')[2]
    require(not scan['errors'], 'read-only mounted media scanned without errors')
    items = request('/api/movies')[2]['items']
    require(len(items) == 1 and items[0]['code'] == 'SMOKE-001', 'fictional NFO imported with correct identity')
    movie = items[0]
    if expect_persisted:
        require(movie['favorite'] and movie['watched'] and movie['rating'] == 4, 'user state survived container recreation')
    require(movie['title'] == '容器测试 & 本地元数据', 'UTF-8 metadata and XML entities preserved')
    require(len(movie['resources']) == 2, 'two STRM files grouped into one movie')
    require(request(movie['poster'])[2] == PNG, 'local poster readable')
    require(len(movie['samples']) == 1 and request(movie['samples'][0])[2] == PNG, 'local sample artwork readable')
    identity = movie['id']
    require(request(f'/api/movies/{identity}/state', {'favorite': True, 'watched': True, 'rating': 4})[0] == 200, 'user state saved to data volume')
    settings = request('/api/settings')[2]
    info = request(f'/Items/{identity}/PlaybackInfo', {}, {'X-Emby-Token': settings['api_key']})
    require(info[0] == 200 and len(info[2]['MediaSources']) == 2, 'LitePan-compatible playback metadata')
    links = request(f'/api/movies/{identity}/play', {'resource_id': movie['resources'][0]['id']})[2]
    play = urlsplit(links['url'])
    path = play.path + '?' + play.query
    status, headers, _ = request(path)
    require(status == 302 and headers['Location'] == TARGET, 'signed playback returns 302 preserving URL signature')
    require(request(path, method='HEAD')[0] == 302, 'HEAD playback request')
    require(links['potplayer'].startswith('potplayer://http') and 'package=is.xyz.mpv;' in links['mpv'], 'external player links')
    movie = request(f'/api/movies/{identity}')[2]
    require(movie['favorite'] and movie['watched'] and movie['rating'] == 4, 'persisted favorite, watch state and rating readable')
    print('All container HTTP checks passed. No request was sent to a real media server.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare').add_argument('directory')
    checks = commands.add_parser('check')
    checks.add_argument('url')
    checks.add_argument('--expect-persisted', action='store_true')
    args = parser.parse_args()
    prepare(args.directory) if args.command == 'prepare' else check(args.url, args.expect_persisted)


if __name__ == '__main__':
    main()
