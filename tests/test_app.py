import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from qmaxhub.scanner import bounded, nfo_metadata, strm_target
from qmaxhub.server import App, make_server

NFO = '''<?xml version="1.0" encoding="UTF-8"?><movie>
<num>DEMO-001</num><title>示例 &amp; 收藏</title><plot><![CDATA[本地资料 <safe>]]></plot>
<premiered>2025-01-02</premiered><runtime>120</runtime><rating>8.4</rating>
<studio>示例工作室</studio><set><name>示例系列</name></set><tag>收藏</tag><genre>剧情</genre>
<actor><name>示例演员</name><thumb>.actors/示例演员.jpg</thumb></actor>
<thumb aspect="poster">poster.jpg</thumb><fanart><thumb>fanart.jpg</thumb></fanart>
</movie>'''


class AppTest(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent.parent / '.test-data'
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.root = Path(self.temp.name) / 'media'
        self.root.mkdir()
        self.folder = self.root / 'DEMO-001'
        self.folder.mkdir()
        (self.folder / 'DEMO-001-CD1.strm').write_text('\ufeff#EXTM3U\nhttp://127.0.0.1:18081/strm/token/1/file/movie.mp4?sign=a%2Fb&x=1\n', encoding='utf-8')
        (self.folder / 'DEMO-001-CD2.strm').write_text('http://example.test/part2.mp4', encoding='utf-8')
        (self.folder / 'movie.nfo').write_text(NFO, encoding='utf-8')
        (self.folder / 'poster.jpg').write_bytes(b'poster-test')
        (self.folder / 'fanart.jpg').write_bytes(b'cover-test')
        (self.folder / '.actors').mkdir()
        (self.folder / '.actors' / '示例演员.jpg').write_bytes(b'actor-test')
        (self.folder / 'extrafanart').mkdir()
        (self.folder / 'extrafanart' / '10.jpg').write_bytes(b'sample-10')
        (self.folder / 'extrafanart' / '2.jpg').write_bytes(b'sample-2')
        self.app = App(Path(self.temp.name) / 'data', [self.root], 'test-password-123', 'http://192.168.1.10:8096', 'http://192.168.1.10:18443')
        self.scan()
        self.server = make_server(self.app, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        if not Path(self.temp.name).resolve().is_relative_to(Path(__file__).resolve().parent.parent / '.test-data'):
            raise RuntimeError('Test cleanup target escaped workspace')
        self.temp.cleanup()

    def scan(self):
        self.assertTrue(self.app.scanner.start())
        deadline = time.monotonic() + 10
        while self.app.scanner.status['running'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.app.scanner.status['running'])

    def request(self, path, body=None, headers=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        extra = {'Cookie': self.cookie, **(headers or {})}
        if body is not None:
            extra['Content-Type'] = 'application/json'
        conn.request(method or ('POST' if body is not None else 'GET'), path, json.dumps(body).encode() if body is not None else None, extra)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(data) if data and 'json' in response.getheader('Content-Type', '') else data)
        conn.close()
        return result

    def login(self):
        status, headers, _ = self.request('/api/login', {'password': 'test-password-123'})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]

    def movie(self):
        return self.app.store.movies()[0]

    def test_metadata_and_multi_part_grouping(self):
        movie = self.movie()
        self.assertEqual(len(self.app.store.movies()), 1)
        self.assertEqual(len(movie['resources']), 2)
        self.assertEqual(movie['title'], '示例 & 收藏')
        self.assertEqual(movie['plot'], '本地资料 <safe>')
        self.assertEqual(movie['series'], '示例系列')
        self.assertEqual(movie['tags'], ['收藏', '剧情'])
        self.assertEqual([Path(s).name for s in movie['samples']], ['2.jpg', '10.jpg'])
        self.assertTrue(movie['actors'][0]['thumb'])
        self.assertEqual(self.app.scanner.status['errors'], [])

    def test_cookie_login_and_public_data_boundaries(self):
        self.assertEqual(self.request('/api/movies')[0], 401)
        self.assertEqual(self.request('/api/login', {'password': 'wrong'})[0], 401)
        self.login()
        status, _, data = self.request('/api/movies')
        self.assertEqual(status, 200)
        movie = data['items'][0]
        self.assertNotIn('nfo', movie)
        self.assertNotIn('target', json.dumps(movie))
        self.assertTrue(movie['poster'].startswith('/api/assets/'))
        self.assertEqual(self.request(movie['poster'])[2], b'poster-test')
        self.request('/api/logout', {})
        self.assertEqual(self.request('/api/movies')[0], 401)

    def test_signed_external_playback_and_emby_contract(self):
        self.login()
        movie = self.movie()
        status, _, links = self.request(f'/api/movies/{movie["id"]}/play', {})
        self.assertEqual(status, 200)
        self.assertTrue(links['url'].startswith('http://192.168.1.10:18443/Videos/'))
        self.assertTrue(links['potplayer'].startswith('potplayer://http://'))
        self.assertIn('package=is.xyz.mpv;', links['mpv'])
        self.assertIn('scheme=http;', links['mpv'])
        self.assertNotIn(self.app.store.get('api_key'), links['url'])
        url = urlsplit(links['url'])
        path = url.path + '?' + url.query
        status, headers, _ = self.request(path)
        self.assertEqual(status, 302)
        self.assertIn('sign=a%2Fb&x=1', headers['Location'])
        self.assertEqual(self.request(path, method='HEAD')[0], 302)
        self.assertEqual(self.request(path[:-1] + ('0' if path[-1] != '0' else '1'))[0], 401)
        key = self.app.store.get('api_key')
        self.assertEqual(self.request('/System/Info')[0], 401)
        self.assertEqual(self.request('/emby/System/Info?api_key=' + key)[0], 200)
        status, _, info = self.request(f'/Items/{movie["id"]}/PlaybackInfo?api_key={key}', {})
        self.assertEqual(status, 200)
        self.assertEqual(len(info['MediaSources']), 2)
        self.assertTrue(info['MediaSources'][0]['Path'].startswith('http://'))
        self.assertFalse(info['MediaSources'][0]['SupportsTranscoding'])
        self.assertEqual(self.request('/Items?Ids=' + movie['id'], headers={'X-Emby-Token': key})[2]['TotalRecordCount'], 1)
        self.assertEqual(self.request('/Library/SelectableMediaFolders?api_key=' + key)[2][0]['Id'], 'library')

    def test_settings_rewrite_and_validation(self):
        self.login()
        self.assertEqual(self.request('/api/settings', {'proxy_url': 'javascript:bad'})[0], 400)
        self.assertEqual(self.request('/api/settings', {'scan_interval': -1})[0], 400)
        self.assertEqual(self.request('/api/settings', {'api_key': 'changed'})[0], 400)
        self.assertEqual(self.request('/api/settings', {'rewrite_from': 'http://127.0.0.1:18081', 'rewrite_to': 'http://192.168.1.10:18443'})[0], 200)
        resource = self.app.store.resource(self.movie()['resources'][0]['id'])
        target = self.app.source(resource)
        self.assertTrue(target.startswith('http://192.168.1.10:18443/strm/'))
        self.assertIn('sign=a%2Fb&x=1', target)
        self.assertEqual(self.request('/api/settings', {'playback_mode': 'direct'})[0], 200)
        links = self.request(f'/api/movies/{self.movie()["id"]}/play', {})[2]
        self.assertTrue(links['url'].startswith('http://192.168.1.10:8096'))

    def test_missing_and_corrupt_files_preserve_user_state(self):
        movie = self.movie()
        self.app.store.state(movie['id'], {'favorite': True, 'watched': True, 'rating': 5})
        added = movie['added']
        (self.folder / 'DEMO-001-CD2.strm').unlink()
        self.scan()
        movie = self.movie()
        self.assertEqual(sum(r['available'] for r in movie['resources']), 1)
        self.assertEqual(movie['added'], added)
        self.assertTrue(movie['favorite'])
        self.assertTrue(movie['watched'])
        self.assertEqual(movie['rating'], 5)
        (self.folder / 'movie.nfo').write_text('<movie><broken>', encoding='utf-8')
        self.scan()
        self.assertFalse(self.movie()['available'])
        self.assertTrue(self.app.scanner.status['errors'])
        (self.folder / 'movie.nfo').write_text(NFO, encoding='utf-8')
        self.scan()
        self.assertTrue(self.movie()['available'])
        self.assertTrue(self.movie()['favorite'])

    def test_no_cross_site_mutations_or_unsafe_nfo(self):
        self.assertEqual(self.request('/api/login', {'password': 'test-password-123'}, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/login', {'password': 'test-password-123'}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
        outside = Path(self.temp.name) / 'private.jpg'
        outside.write_text('secret')
        (self.folder / 'movie.nfo').write_text('<movie><num>DEMO-001</num><thumb aspect="poster">../../private.jpg</thumb></movie>')
        self.scan()
        self.assertTrue(self.app.scanner.status['errors'])
        with self.assertRaises(ValueError):
            bounded(outside, self.root)
        (self.folder / 'movie.nfo').write_text('<!DOCTYPE movie [<!ENTITY x "boom">]><movie><title>&x;</title></movie>')
        self.scan()
        self.assertIn('DTD', self.app.scanner.status['errors'][0]['message'])

    def test_fresh_strm_read_and_token_scope(self):
        self.login()
        m = self.movie()
        links = self.request(f'/api/movies/{m["id"]}/play', {})[2]
        url = urlsplit(links['url'])
        (self.folder / 'DEMO-001-CD1.strm').write_text('https://example.test/new.mp4?token=fresh')
        self.assertEqual(self.request(url.path + '?' + url.query)[1]['Location'], 'https://example.test/new.mp4?token=fresh')
        first, second = m['resources']
        self.assertFalse(self.app.verify(m['id'], second['id'], self.app.ticket(m['id'], first['id'])))
        expires = int(time.time()) - 1
        self.assertFalse(self.app.verify(m['id'], first['id'], f'{expires}.{self.app.sign(m["id"],first["id"],expires)}'))
        (self.folder / 'DEMO-001-CD1.strm').write_text('file:///etc/passwd')
        with self.assertRaises(ValueError):
            strm_target(self.folder / 'DEMO-001-CD1.strm')

    def test_password_change_revokes_existing_sessions(self):
        self.login()
        self.assertEqual(self.request('/api/movies')[0], 200)
        App(Path(self.temp.name) / 'data', [self.root], 'new-password-456')
        self.assertEqual(self.request('/api/movies')[0], 401)

    def test_shared_part_nfo_and_metadata_change_keep_identity(self):
        old = self.movie()
        self.app.store.state(old['id'], {'favorite': True})
        (self.folder / 'movie.nfo').rename(self.folder / 'DEMO-001.nfo')
        self.scan()
        self.assertEqual(self.app.scanner.status['errors'], [])
        current = self.movie()
        self.assertEqual(current['id'], old['id'])
        self.assertEqual(len(current['resources']), 2)
        self.assertTrue(current['favorite'])
        self.assertEqual(current['title'], '示例 & 收藏')

    def test_proxy_supports_custom_ports_https_and_path_prefixes(self):
        self.login()
        movie = self.movie()
        for address in ('https://proxy.example:19443/media', 'https://proxy.example/gateway', 'http://proxy.example:18081'):
            with self.subTest(address=address):
                status, _, settings = self.request('/api/settings', {'playback_mode': 'proxy', 'proxy_url': address})
                self.assertEqual(status, 200)
                self.assertEqual(settings['proxy_url'], address)
                links = self.request(f'/api/movies/{movie["id"]}/play', {})[2]
                self.assertTrue(links['url'].startswith(address + '/Videos/'))
                self.assertTrue(links['potplayer'].startswith('potplayer://' + address + '/Videos/'))
                self.assertIn('scheme=' + urlsplit(address).scheme + ';', links['mpv'])
        for address in ('http://proxy.example:bad', 'http://proxy.example:65536', 'http://proxy.example:0'):
            self.assertEqual(self.request('/api/settings', {'proxy_url': address})[0], 400)
        self.assertEqual(self.request('/api/settings', {'proxy_url': ''})[0], 400)

    def test_provider_settings_migrate_without_resetting_user_data(self):
        self.login()
        movie = self.movie()
        self.app.store.state(movie['id'], {'favorite': True, 'watched': True, 'rating': 4})
        old_keys = {key: self.app.store.get(key) for key in ('api_key', 'signing_key', 'server_id')}
        resource_id = movie['resources'][0]['id']
        ticket = self.app.ticket(movie['id'], resource_id)
        with self.app.store.connect() as db:
            db.execute('DELETE FROM settings WHERE key=?', ('proxy_url',))
        self.app.store.put({'litepan_url': 'https://proxy.example:19443/streaming', 'playback_mode': 'litepan'})
        data = Path(self.temp.name) / 'data'
        for _ in range(2):
            migrated = App(data, [self.root], 'test-password-123')
            self.assertEqual(migrated.settings()['proxy_url'], 'https://proxy.example:19443/streaming')
            self.assertEqual(migrated.settings()['playback_mode'], 'proxy')
            self.assertIsNone(migrated.store.get('litepan_url'))
            self.assertNotIn('litepan', json.dumps(migrated.settings()))
            for key, value in old_keys.items():
                self.assertEqual(migrated.store.get(key), value)
            self.assertTrue(migrated.verify(movie['id'], resource_id, ticket))
            self.assertTrue(migrated.store.movie(movie['id'])['favorite'])
            self.assertTrue(migrated.store.movie(movie['id'])['watched'])
            self.assertEqual(migrated.store.movie(movie['id'])['rating'], 4)
        self.server.app = migrated
        self.assertEqual(self.request('/api/movies')[0], 200)
        links = self.request(f'/api/movies/{movie["id"]}/play', {})[2]
        self.assertTrue(links['url'].startswith('https://proxy.example:19443/streaming/Videos/'))

    def test_migration_preserves_newer_proxy_configuration(self):
        self.app.store.put({'litepan_url': 'http://retired.example:18081',
                            'proxy_url': 'https://new-proxy.example:19443/media', 'playback_mode': 'direct'})
        migrated = App(Path(self.temp.name) / 'data', [self.root], 'test-password-123', proxy_url='http://initial.example')
        self.assertEqual(migrated.settings()['proxy_url'], 'https://new-proxy.example:19443/media')
        self.assertEqual(migrated.settings()['playback_mode'], 'direct')
        self.assertIsNone(migrated.store.get('litepan_url'))


if __name__ == '__main__':
    unittest.main()
