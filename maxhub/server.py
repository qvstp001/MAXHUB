import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from . import __version__
from .scanner import IMAGE_EXT, Scanner, bounded, strm_target
from .store import Store
from .artwork import Artwork

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
    def __init__(self, data, roots, public_url='http://localhost:8096', proxy_url=''):
        self.store = Store(data)
        self.artwork = Artwork(data)
        self.scanner = Scanner(self.store, roots)
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
        allowed = {'public_url', 'proxy_url', 'playback_mode', 'rewrite_from', 'rewrite_to', 'scan_interval'}
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
        self.store.put(values)

    def source(self, resource):
        root = Path(resource['root'])
        if root not in self.scanner.roots:
            raise ValueError('媒体目录已不在当前配置内')
        target = strm_target(bounded(resource['path'], root))
        old, new = self.store.get('rewrite_from'), self.store.get('rewrite_to')
        if old and (target == old or target.startswith(old + '/') or target.startswith(old + '?')):
            target = new + target[len(old):]
        return target

    def public_movie(self, movie):
        def resource(row):
            path = Path(row['path'])
            try:
                folder = path.relative_to(Path(row['root'])).parent.as_posix()
                folder = '' if folder == '.' else folder
            except ValueError:
                folder = None
            return dict(id=row['id'], name=path.name, root=row['root'], folder=folder, available=bool(row['available']))
        item = {k: v for k, v in movie.items() if k not in ('nfo', 'poster', 'cover', 'samples', 'actors', 'resources')}
        prefix = f'/api/assets/{movie["id"]}'
        item.update(poster=prefix + '/poster' if movie['poster'] else None,
                    cover=prefix + '/cover' if movie['cover'] else None,
                    samples=[f'{prefix}/sample/{i}' for i in range(len(movie['samples']))],
                    actors=[{**a, 'thumb': f'{prefix}/actor/{i}' if a['thumb'] else None} for i, a in enumerate(movie['actors'])],
                    resources=[resource(r) for r in movie['resources']])
        item['resource_count'] = len(movie['resources'])
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
                            'Protocol': 'Http', 'IsRemote': True, 'Container': 'mp4', 'Type': 'Default',
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
    server_version = 'MAXHUB/' + __version__

    @property
    def app(self):
        return self.server.app

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Avoid recording signed playback URLs or STRM tokens.
        logging.info('%s %s %s', self.client_address[0], self.command, urlsplit(self.path).path)

    def send(self, status=200, body=None, headers=None, content_type='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None and not isinstance(body, bytes) else (body or b'')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        if 'Cache-Control' not in (headers or {}):
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

    def emby_auth(self, query):
        token = query.get('api_key', query.get('apikey', query.get('x-emby-token', [''])))[0] or self.headers.get('X-Emby-Token') or self.headers.get('X-MediaBrowser-Token') or ''
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
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
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
            # Browser mutations require JSON and reject cross-site requests.
            origin = self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urlsplit(origin).netloc != self.headers.get('Host')):
                return self.send(403, {'error': '不允许跨站请求'})
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send(415, {'error': '需要 application/json'})
        if path == '/health' and not post:
            return self.send(body={'status': 'ok', 'version': __version__})
        if path == '/favicon.ico' and not post:
            return self.send(204)
        if path in ('/', '/app.js', '/styles.css', '/catalog-controls.css', '/profiles.css', '/theme.js', '/browse-state.js', '/folder-browser.js', '/filter-picker.js', '/movie-detail.js', '/favicon.svg') and not post:
            file = WEB / ('index.html' if path == '/' else path[1:])
            return self.send(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'text/plain',
                             headers={'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        if path.startswith('/api/'):
            return self.api(path, query, post)

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
            return self.send(302, headers={'Location': self.app.source(resource)})
        if path.lower() == '/system/info/public' and not post:
            return self.send(body={'ServerName': 'MAXHUB', 'Version': __version__, 'Id': self.app.store.get('server_id')})
        if not self.emby_auth(query):
            return self.send(401, {'error': '需要媒体服务 API Key'})
        lower = path.lower()
        if lower == '/system/info' and not post:
            return self.send(body={'ServerName': 'MAXHUB', 'Version': __version__, 'Id': self.app.store.get('server_id'), 'ProductName': 'MAXHUB', 'SupportsLibraryMonitor': False})
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
            if ids[0]:
                if len(ids) > 100:
                    raise ValueError('一次最多查询 100 个影片')
                movies = [movie for identity in dict.fromkeys(ids) if (movie := self.app.store.movie(identity))]
            else:
                listing = self.app.store.catalog.movies(page=1, limit=min(100, max(1, int(query.get('limit', ['60'])[0]))))
                movies = [self.app.store.movie(m['id']) for m in listing['items']]
            return self.send(body={'Items': [self.app.emby_item(m) for m in movies],
                                   'TotalRecordCount': len(movies) if ids[0] else listing['total']})
        return self.send(404, {'error': '接口不存在；MAXHUB 仅提供播放对接所需的 Emby 兼容接口子集'})

    def api(self, path, query, post):
        if path == '/api/settings':
            if post:
                self.app.save_settings(self.body())
            return self.send(body=self.app.settings())
        if path == '/api/scan':
            if post:
                values = self.body()
                if set(values) - {'full'} or type(values.get('full', False)) is not bool:
                    raise ValueError('扫描选项 full 必须为布尔值')
                self.app.scanner.start(force=values.get('full', False))
            status = self.app.scanner.status
            if not status['running'] and not status['finished']:
                status = self.app.store.get('last_scan', status)
            return self.send(202 if post else 200, status)
        if path == '/api/movies' and not post:
            value = lambda key, default='': query.get(key, [default])[0]
            if value('recursive', '1') not in ('0', '1'):
                raise ValueError('recursive 只能为 0 或 1')
            return self.send(body=self.app.store.catalog.movies(
                page=int(value('page', '1')), limit=int(value('limit', '60')),
                search=value('search'), sort=value('sort', 'added'), status=value('status'),
                favorite=value('favorite') == '1', actor=value('actor'), tag=query.get('tag', []),
                studio=value('studio'), series=value('series'), root=value('root'), folder=value('folder'),
                recursive=value('recursive', '1') == '1'))
        if path == '/api/stats' and not post:
            return self.send(body=self.app.store.catalog.stats())
        if path == '/api/facets' and not post:
            return self.send(body=self.app.store.catalog.facets(query.get('kind', ['actor'])[0],
                int(query.get('page', ['1'])[0]), int(query.get('limit', ['100'])[0]), query.get('search', [''])[0]))
        if path == '/api/entities' and not post:
            entity = self.app.store.catalog.entity(query.get('kind', [''])[0], query.get('name', [''])[0])
            return self.send(body=entity) if entity else self.send(404, {'error': '本地媒体库中未找到该资料'})
        if path == '/api/folders' and not post:
            return self.send(body=self.app.store.catalog.folders(query.get('root', [''])[0], query.get('path', [''])[0],
                int(query.get('page', ['1'])[0]), int(query.get('limit', ['100'])[0]), query.get('search', [''])[0]))
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
                base = self.app.store.get('proxy_url') if self.app.store.get('playback_mode') == 'proxy' else self.app.store.get('public_url')
                params = urlencode({'MediaSourceId': resource['id'], 'Static': 'true', 'play_token': self.app.ticket(movie['id'], resource['id'])})
                play_url = f'{base}/Videos/{movie["id"]}/stream?{params}'
                self.app.store.state(movie['id'], {'last_played': time.time()})
                parts = urlsplit(play_url)
                intent = f'intent://{parts.netloc}{parts.path}?{parts.query}#Intent;scheme={parts.scheme};type=video/any;package=is.xyz.mpv;end;'
                return self.send(body={'url': play_url, 'potplayer': 'potplayer://' + play_url, 'mpv': intent, 'expires_in': 43200})
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
            stat = resolved.stat()
            if stat.st_size > 32 * 1024 * 1024:
                return self.send(413)
            preset = query.get('size', [''])[0]
            if preset not in ('', 'card', 'avatar', 'preview'):
                raise ValueError('无效的图片尺寸')
            etag = f'"{stat.st_mtime_ns:x}-{stat.st_ctime_ns:x}-{stat.st_size:x}-{preset}-v1"'
            headers = {'Cache-Control': 'private, no-cache', 'ETag': etag, 'Vary': 'Accept-Encoding'}
            if self.headers.get('If-None-Match') == etag:
                return self.send(304, headers=headers)
            if preset:
                dimensions = (320, 200) if preset == 'preview' else (160, 160) if preset == 'avatar' else (360, 540) if field == 'poster' else (720, 480)
                thumbnail = self.app.artwork.thumbnail(resolved, etag, dimensions)
                if thumbnail is not None:
                    return self.send(body=thumbnail, headers=headers, content_type='image/webp')
            return self.send(body=resolved.read_bytes(), headers=headers,
                             content_type=mimetypes.guess_type(resolved)[0] or 'image/jpeg')
        return self.send(404, {'error': '接口不存在'})


def make_server(app, host='0.0.0.0', port=8096):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = app
    return server
