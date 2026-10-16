import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from . import __version__
from .scanner import IMAGE_EXT, MEDIA_EXT, VIDEO_EXT, Scanner, bounded, strm_target
from .store import Store

WEB = Path(__file__).resolve().parent.parent / 'web'


def base_url(value, optional=False):
    if not isinstance(value, str):
        raise ValueError('地址必须是文本')
    value = value.strip().rstrip('/')
    if not value and optional:
        return ''
    url = urlsplit(value)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() for c in value):
        raise ValueError('请输入完整的 HTTP(S) 地址，不能带账号、查询参数或片段')
    try:
        port = url.port
    except ValueError:
        raise ValueError('地址端口必须是 1–65535 范围内的整数') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('地址端口必须是 1–65535 范围内的整数')
    return value


class App:
    def __init__(self, data, roots, password, public_url='http://localhost:8096', proxy_url=''):
        if len(password) < 10:
            raise ValueError('ADMIN_PASSWORD 至少需要 10 个字符')
        self.store = Store(data)
        self.scanner = Scanner(self.store, self.store.get('roots', roots))
        self.password_hash = hashlib.scrypt(password.encode(), salt=b'qmaxhub-login-v1', n=16384, r=8, p=1)
        fingerprint = hmac.new(self.store.get('signing_key').encode(), self.password_hash, hashlib.sha256).hexdigest()
        if self.store.get('password_fingerprint') != fingerprint:
            with self.store.connect() as db:
                db.execute('DELETE FROM sessions')
            self.store.put({'password_fingerprint': fingerprint})
        self.secure_cookie = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
        self.auth_lock = threading.Lock()
        self.failures = {}
        initial = {'public_url': base_url(public_url), 'proxy_url': base_url(proxy_url, True),
                   'playback_mode': 'proxy' if proxy_url else 'direct',
                   'rewrite_from': '', 'rewrite_to': '', 'scan_interval': max(0, int(os.getenv('SCAN_INTERVAL', '1800')))}
        self.store.put({k: v for k, v in initial.items() if self.store.get(k) is None})

    def sign(self, movie, resource, expires):
        return hmac.new(self.store.get('signing_key').encode(), f'{movie}:{resource}:{expires}'.encode(), hashlib.sha256).hexdigest()

    def ticket(self, movie, resource):
        expires = int(time.time()) + 12 * 3600
        return f'{expires}.{self.sign(movie, resource, expires)}'

    def verify(self, movie, resource, ticket):
        try:
            expires, signature = ticket.split('.')
            return int(expires) > time.time() and hmac.compare_digest(signature, self.sign(movie, resource, int(expires)))
        except (ValueError, TypeError):
            return False

    def settings(self):
        keys = ('public_url', 'proxy_url', 'playback_mode', 'rewrite_from', 'rewrite_to', 'scan_interval', 'api_key')
        return {**{k: self.store.get(k) for k in keys}, 'roots': [str(r) for r in self.scanner.roots], 'version': __version__}

    def save_settings(self, values):
        values = dict(values)
        allowed = {'public_url', 'proxy_url', 'playback_mode', 'rewrite_from', 'rewrite_to', 'scan_interval', 'roots'}
        if set(values) - allowed:
            raise ValueError('包含不能修改的设置')
        for key in ('public_url', 'proxy_url', 'rewrite_from', 'rewrite_to'):
            if key in values:
                values[key] = base_url(values[key], key != 'public_url')
        merged = {**self.settings(), **values}
        if merged['playback_mode'] not in ('direct', 'proxy'):
            raise ValueError('无效的播放模式')
        if merged['playback_mode'] == 'proxy' and not merged['proxy_url']:
            raise ValueError('302 反代模式需要填写客户端可访问的播放入口，端口按实际部署配置')
        if bool(merged['rewrite_from']) != bool(merged['rewrite_to']):
            raise ValueError('地址替换的来源和目标需要同时填写')
        if type(merged['scan_interval']) is not int or not 0 <= merged['scan_interval'] <= 604800:
            raise ValueError('扫描间隔应为 0–604800 秒，0 表示关闭')
        if 'roots' not in values:
            self.store.put(values)
            return
        roots = values['roots']
        if not isinstance(roots, list) or len(roots) > 64 or any(not isinstance(r, str) or not r.strip() for r in roots):
            raise ValueError('媒体来源必须是目录列表，最多 64 项；清空列表可移除全部来源')
        paths = []
        for value in roots:
            path = Path(value.strip()).expanduser()
            if not path.is_absolute():
                raise ValueError('媒体来源必须使用绝对路径')
            try:
                path = path.resolve()
                if not path.is_dir():
                    raise ValueError(f'目录不存在或不可访问：{path}')
                # Check traversal permission without loading a potentially large directory.
                with os.scandir(path) as entries:
                    next(entries, None)
            except OSError as error:
                raise ValueError(f'无法读取媒体目录：{path}') from error
            if path not in paths:
                paths.append(path)
        values['roots'] = [str(p) for p in paths]
        if not self.scanner.lock.acquire(blocking=False):
            raise ValueError('正在扫描，请等待扫描完成后再修改媒体来源')
        try:
            with self.store.connect() as db:
                db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',
                               [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()])
                for row in db.execute('SELECT DISTINCT root FROM resources').fetchall():
                    if Path(row['root']) not in paths:
                        db.execute('UPDATE resources SET available=0 WHERE root=?', (row['root'],))
            self.scanner.roots = paths
        finally:
            self.scanner.lock.release()

    def media_path(self, resource):
        root = Path(resource['root'])
        if root not in self.scanner.roots:
            raise ValueError('媒体目录已不在当前配置内')
        path = bounded(resource['path'], root)
        if path.suffix.lower() not in MEDIA_EXT:
            raise ValueError('不支持的媒体文件格式')
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def stream_url(self, movie_id, resource_id):
        params = urlencode({'MediaSourceId': resource_id, 'Static': 'true', 'play_token': self.ticket(movie_id, resource_id)})
        return f'{self.store.get("public_url")}/Videos/{movie_id}/stream?{params}'

    def source(self, resource):
        path = self.media_path(resource)
        if path.suffix.lower() in VIDEO_EXT:
            return self.stream_url(resource['movie_id'], resource['id'])
        target = strm_target(path)
        old, new = self.store.get('rewrite_from'), self.store.get('rewrite_to')
        if old and (target == old or target.startswith(old + '/') or target.startswith(old + '?')):
            target = new + target[len(old):]
        return target

    def public_movie(self, movie):
        item = {k: v for k, v in movie.items() if k not in ('nfo', 'poster', 'cover', 'samples', 'actors', 'resources')}
        prefix = f'/api/assets/{movie["id"]}'
        item.update(poster=prefix + '/poster' if movie['poster'] else None,
                    cover=prefix + '/cover' if movie['cover'] else None,
                    samples=[f'{prefix}/sample/{i}' for i in range(len(movie['samples']))],
                    actors=[{**a, 'thumb': f'{prefix}/actor/{i}' if a['thumb'] else None} for i, a in enumerate(movie['actors'])],
                    resources=[{'id': r['id'], 'name': Path(r['path']).name, 'root': r['root'],
                                'format': Path(r['path']).suffix[1:].upper(),
                                'kind': 'strm' if Path(r['path']).suffix.lower() == '.strm' else 'local',
                                'available': bool(r['available'])} for r in movie['resources']])
        return item

    def emby_item(self, movie):
        sources = []
        for r in movie['resources']:
            if not r['available']:
                continue
            try:
                target = self.source(self.store.resource(r['id']))
            except (ValueError, OSError):
                continue
            sources.append({'Id': r['id'], 'Name': Path(r['path']).stem, 'Path': target,
                            'Protocol': 'Http', 'IsRemote': True,
                            'Container': Path(r['path']).suffix[1:].lower() if Path(r['path']).suffix.lower() in VIDEO_EXT else 'mp4', 'Type': 'Default',
                            'SupportsDirectPlay': True, 'SupportsDirectStream': True, 'SupportsTranscoding': False,
                            'MediaStreams': [], 'RunTimeTicks': int(movie['runtime'] * 60 * 10000000),
                            'DirectStreamUrl': f'/Videos/{movie["id"]}/stream?MediaSourceId={r["id"]}'})
        return {'Id': movie['id'], 'Name': movie['title'], 'Type': 'Movie', 'MediaType': 'Video',
                'Path': sources[0]['Path'] if sources else '', 'MediaSources': sources,
                'Overview': movie['plot'], 'ProviderIds': {'num': movie['code']},
                'IsFolder': False, 'UserData': {'Played': movie['watched'], 'IsFavorite': movie['favorite']}}

    def schedule(self, stop):
        self.scanner.start()
        last = time.monotonic()
        while not stop.wait(5):
            interval = self.store.get('scan_interval', 1800)
            if interval and time.monotonic() - last >= interval and self.scanner.start():
                last = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    server_version = 'QMaxHub/' + __version__

    @property
    def app(self):
        return self.server.app

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Avoid recording session credentials, signed playback URLs or STRM tokens.
        logging.info('%s %s %s', self.client_address[0], self.command, urlsplit(self.path).path)

    def send(self, status=200, body=None, headers=None, content_type='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None and not isinstance(body, bytes) else (body or b'')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 <= length <= 65536:
            raise ValueError('请求体过大')
        result = json.loads(self.rfile.read(length) or b'{}')
        if not isinstance(result, dict):
            raise ValueError('请求体必须是 JSON 对象')
        return result

    def send_video(self, path):
        with path.open('rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            start, end, status = 0, size - 1, 200
            requested = self.headers.get('Range')
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
                valid = bool(match and any(match.groups()) and size)
                if valid:
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        suffix = int(last)
                        start = max(0, size - suffix)
                        valid = suffix > 0
                    valid = valid and 0 <= start <= end < size
                if not valid:
                    return self.send(416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
                status = 206
            length = max(0, end - start + 1)
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            stream.seek(start)
            while length:
                chunk = stream.read(min(length, 1024 * 1024))
                if not chunk:
                    break
                self.wfile.write(chunk)
                length -= len(chunk)

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['qmaxhub_session'].value
        except (KeyError, ValueError):
            return None
        with self.app.store.connect() as db:
            row = db.execute('SELECT token FROM sessions WHERE token=? AND expires>?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return token if row else None

    def emby_auth(self, query):
        token = query.get('api_key', query.get('x-emby-token', ['']))[0] or self.headers.get('X-Emby-Token') or self.headers.get('X-MediaBrowser-Token') or ''
        match = re.search(r'Token="([^"]+)"', self.headers.get('Authorization', '') + self.headers.get('X-Emby-Authorization', ''), re.I)
        token = token or (match.group(1) if match else '')
        return hmac.compare_digest(token, self.app.store.get('api_key'))

    def do_GET(self):
        self.dispatch()

    def do_HEAD(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            self.route()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except (ValueError, UnicodeError, json.JSONDecodeError) as error:
            self.send(400, {'error': str(error)})
        except FileNotFoundError:
            self.send(404, {'error': '文件已不可用，请重新扫描媒体库'})
        except Exception:
            logging.exception('Request failed: %s', urlsplit(self.path).path)
            self.send(500, {'error': '服务内部错误，请查看服务日志'})

    def route(self):
        url = urlsplit(self.path)
        path = url.path.rstrip('/') or '/'
        query = {k.lower(): v for k, v in parse_qs(url.query).items()}
        post = self.command == 'POST'
        if post and path.startswith('/api/'):
            # Browser mutations require JSON and reject cross-site requests, including login.
            origin = self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urlsplit(origin).netloc != self.headers.get('Host')):
                return self.send(403, {'error': '不允许跨站请求'})
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send(415, {'error': '需要 application/json'})
        if path == '/health' and not post:
            return self.send(body={'status': 'ok', 'version': __version__})
        if path in ('/', '/app.js', '/styles.css') and not post:
            file = WEB / ('index.html' if path == '/' else path[1:])
            return self.send(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'text/plain',
                             headers={'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        if path == '/api/login' and post:
            return self.login()
        session = self.session()
        if path == '/api/session' and not post:
            return self.send(body={'authenticated': bool(session)})
        if path.startswith('/api/'):
            if not session:
                return self.send(401, {'error': '请先登录'})
            return self.api(path, query, post, session)

        if path.lower().startswith('/emby/'):
            path = path[5:]
        stream = re.fullmatch(r'/Videos/([^/]+)/(?:stream|original)(?:\.[\w]+)?', path, re.I)
        if stream and not post:
            movie_id = stream[1]
            resource_id = query.get('mediasourceid', [''])[0]
            ticket = query.get('play_token', [''])[0]
            if not (self.emby_auth(query) or self.app.verify(movie_id, resource_id, ticket)):
                return self.send(401, {'error': '播放链接已失效，请从媒体库重新打开'})
            resource = self.app.store.resource(resource_id)
            if not resource or resource['movie_id'] != movie_id or not resource['available']:
                return self.send(404, {'error': '播放资源不可用'})
            file = self.app.media_path(resource)
            if file.suffix.lower() in VIDEO_EXT:
                return self.send_video(file)
            return self.send(302, headers={'Location': self.app.source(resource)})
        if path.lower() == '/system/info/public' and not post:
            return self.send(body={'ServerName': 'QMaxHub', 'Version': __version__, 'Id': self.app.store.get('server_id')})
        if not self.emby_auth(query):
            return self.send(401, {'error': '需要媒体服务 API Key'})
        lower = path.lower()
        if lower == '/system/info' and not post:
            return self.send(body={'ServerName': 'QMaxHub', 'Version': __version__, 'Id': self.app.store.get('server_id'), 'ProductName': 'QMaxHub', 'SupportsLibraryMonitor': False})
        if lower in ('/library/selectablemediafolders', '/library/virtualfolders') and not post:
            return self.send(body=[{'Id': 'library', 'ItemId': 'library', 'Name': '影片库', 'CollectionType': 'movies', 'Locations': [str(r) for r in self.app.scanner.roots]}])
        if lower == '/scheduledtasks' and not post:
            return self.send(body=[{'Id': 'scan', 'Name': '扫描媒体库', 'Key': 'RefreshLibrary', 'State': 'Running' if self.app.scanner.status['running'] else 'Idle'}])
        if post and lower in ('/scheduledtasks/running/scan', '/library/refresh', '/items/library/refresh'):
            self.app.scanner.start()
            return self.send(204)
        match = re.fullmatch(r'/(?:Users/[^/]+/)?Items/([^/]+)(/PlaybackInfo)?', path, re.I)
        if match and (not post or match[2]):
            movie = self.app.store.movie(match[1])
            if not movie:
                return self.send(404, {'error': '影片不存在'})
            item = self.app.emby_item(movie)
            return self.send(body={'MediaSources': item['MediaSources'], 'PlaySessionId': secrets.token_hex(16)} if match[2] else item)
        if lower == '/items' and not post:
            ids = query.get('ids', [''])[0].split(',')
            movies = [m for m in self.app.store.movies() if not ids[0] or m['id'] in ids]
            return self.send(body={'Items': [self.app.emby_item(m) for m in movies], 'TotalRecordCount': len(movies)})
        return self.send(404, {'error': '接口不存在；QMaxHub 仅提供播放对接所需的 Emby 兼容接口子集'})

    def login(self):
        password = self.body().get('password', '')
        if not isinstance(password, str):
            raise ValueError('密码格式错误')
        ip, now = self.client_address[0], time.time()
        with self.app.auth_lock:
            self.app.failures = {key: value for key, value in self.app.failures.items() if now - value[1] < 300}
            count, start = self.app.failures.get(ip, (0, now))
            if count >= 10:
                return self.send(429, {'error': '尝试次数过多，请五分钟后重试'})
            candidate = hashlib.scrypt(password.encode(), salt=b'qmaxhub-login-v1', n=16384, r=8, p=1)
            if not hmac.compare_digest(candidate, self.app.password_hash):
                self.app.failures[ip] = (count + 1, start)
                return self.send(401, {'error': '密码不正确'})
            self.app.failures.pop(ip, None)
        token = secrets.token_urlsafe(32)
        with self.app.store.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (now,))
            db.execute('INSERT INTO sessions VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(), now + 604800))
        cookie = f'qmaxhub_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800' + ('; Secure' if self.app.secure_cookie else '')
        return self.send(body={'ok': True}, headers={'Set-Cookie': cookie})

    def api(self, path, query, post, session):
        if path == '/api/logout' and post:
            with self.app.store.connect() as db:
                db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(session.encode()).hexdigest(),))
            return self.send(body={'ok': True}, headers={'Set-Cookie': 'qmaxhub_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
        if path == '/api/settings':
            if post:
                self.app.save_settings(self.body())
            return self.send(body=self.app.settings())
        if path == '/api/scan':
            if post:
                self.app.scanner.start()
            status = self.app.scanner.status
            if not status['running'] and not status['finished']:
                status = self.app.store.get('last_scan', status)
            return self.send(202 if post else 200, status)
        if path == '/api/movies' and not post:
            movies = [self.app.public_movie(m) for m in self.app.store.movies()]
            return self.send(body={'items': movies})
        match = re.fullmatch(r'/api/movies/([^/]+)(?:/(state|play))?', path)
        if match:
            movie = self.app.store.movie(match[1])
            if not movie:
                return self.send(404, {'error': '影片不存在'})
            if match[2] == 'state' and post:
                values = self.body()
                if 'last_played' in values:
                    raise ValueError('不能直接修改播放历史')
                self.app.store.state(movie['id'], values)
                return self.send(body=self.app.public_movie(self.app.store.movie(movie['id'])))
            if match[2] == 'play' and post:
                resource_id = self.body().get('resource_id')
                resource = next((r for r in movie['resources'] if r['available'] and (not resource_id or resource_id == r['id'])), None)
                if not resource:
                    return self.send(404, {'error': '没有可播放资源，请重新扫描'})
                self.app.source(self.app.store.resource(resource['id']))
                local = Path(resource['path']).suffix.lower() in VIDEO_EXT
                play_url = self.app.stream_url(movie['id'], resource['id'])
                if not local and self.app.store.get('playback_mode') == 'proxy':
                    play_url = self.app.store.get('proxy_url') + play_url[len(self.app.store.get('public_url')):]
                self.app.store.state(movie['id'], {'last_played': time.time()})
                parts = urlsplit(play_url)
                intent = f'intent://{parts.netloc}{parts.path}?{parts.query}#Intent;scheme={parts.scheme};type=video/any;package=is.xyz.mpv;end;'
                return self.send(body={'url': play_url, 'potplayer': 'potplayer://' + play_url, 'mpv': intent,
                                       'kind': 'local' if local else 'strm', 'expires_in': 43200})
            if not match[2] and not post:
                return self.send(body=self.app.public_movie(movie))
        asset = re.fullmatch(r'/api/assets/([^/]+)/(poster|cover|sample|actor)(?:/(\d+))?', path)
        if asset and not post:
            movie = self.app.store.movie(asset[1])
            if not movie:
                return self.send(404)
            field, index = asset[2], int(asset[3] or 0)
            try:
                file = movie['samples'][index] if field == 'sample' else movie['actors'][index]['thumb'] if field == 'actor' else movie[field]
            except IndexError:
                return self.send(404)
            if not file:
                return self.send(404)
            resolved = Path(file).resolve()
            if resolved.suffix.lower() not in IMAGE_EXT or not any(resolved.is_relative_to(r) for r in self.app.scanner.roots):
                return self.send(403)
            if resolved.stat().st_size > 32 * 1024 * 1024:
                return self.send(413)
            return self.send(body=resolved.read_bytes(), content_type=mimetypes.guess_type(resolved)[0] or 'image/jpeg')
        return self.send(404, {'error': '接口不存在'})


def make_server(app, host='0.0.0.0', port=8096):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = app
    return server
