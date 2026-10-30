import http.client
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import urlencode
from unittest.mock import patch

from PIL import Image

from maxhub.scanner import bounded, nfo_metadata, strm_target
from maxhub.server import App, make_server

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
        self.app = App(Path(self.temp.name) / 'data', [self.root], 'http://192.168.1.10:8096', 'http://192.168.1.10:18443')
        self.scan()
        self.server = make_server(self.app, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        if not Path(self.temp.name).resolve().is_relative_to(Path(__file__).resolve().parent.parent / '.test-data'):
            raise RuntimeError('Test cleanup target escaped workspace')
        self.temp.cleanup()

    def scan(self, force=False):
        self.assertTrue(self.app.scanner.start(force=force))
        deadline = time.monotonic() + 10
        while self.app.scanner.status['running'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.app.scanner.status['running'])

    def request(self, path, body=None, headers=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        extra = dict(headers or {})
        if body is not None:
            extra['Content-Type'] = 'application/json'
        conn.request(method or ('POST' if body is not None else 'GET'), path, json.dumps(body).encode() if body is not None else None, extra)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(data) if data and 'json' in response.getheader('Content-Type', '') else data)
        conn.close()
        return result

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

    def test_lan_access_without_login_preserves_data_boundaries(self):
        status, _, data = self.request('/api/movies')
        self.assertEqual(status, 200)
        movie = data['items'][0]
        self.assertNotIn('nfo', movie)
        self.assertNotIn('target', json.dumps(movie))
        self.assertTrue(movie['poster'].startswith('/api/assets/'))
        self.assertEqual(self.request(movie['poster'])[2], b'poster-test')

    def test_signed_external_playback_and_emby_contract(self):
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
        self.assertEqual(self.request('/api/settings', {}, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/settings', {}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
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

    def test_legacy_password_environment_does_not_enable_a_login_gate(self):
        with patch.dict(os.environ, {'ADMIN_PASSWORD': 'ignored-old-password', 'COOKIE_SECURE': 'true'}):
            self.server.app = App(Path(self.temp.name) / 'data', [self.root])
        status, headers, _ = self.request('/api/movies')
        self.assertEqual(status, 200)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.request('/api/settings')[0], 200)
        self.assertEqual(self.request('/api/login', {})[0], 404)
        self.assertEqual(self.request('/api/session')[0], 404)

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
            migrated = App(data, [self.root])
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
        migrated = App(Path(self.temp.name) / 'data', [self.root], proxy_url='http://initial.example')
        self.assertEqual(migrated.settings()['proxy_url'], 'https://new-proxy.example:19443/media')
        self.assertEqual(migrated.settings()['playback_mode'], 'direct')
        self.assertIsNone(migrated.store.get('litepan_url'))

    def test_browse_queries_are_bounded_and_never_load_entire_library(self):
        with patch.object(self.app.store, 'movies', side_effect=AssertionError('Full library load')):
            status, _, page = self.request('/api/movies?limit=1&page=1')
            self.assertEqual(status, 200)
            self.assertEqual(page['total'], 1)
            self.assertEqual(page['limit'], 1)
            self.assertEqual(page['items'][0]['resource_count'], 2)
            for field in ('plot', 'resources', 'samples', 'nfo', 'tags'):
                self.assertNotIn(field, page['items'][0])
            identity = page['items'][0]['id']
            detail = self.request('/api/movies/' + identity)[2]
            self.assertEqual(len(detail['resources']), 2)
            for filters in ({'search': 'DEMO-001'}, {'actor': '示例演员'}, {'studio': '示例工作室'},
                            {'tag': '剧情'}, {'actor': '示例演员', 'studio': '示例工作室', 'tag': '剧情'}):
                with self.subTest(filters=filters):
                    self.assertEqual(self.request('/api/movies?' + urlencode(filters))[2]['total'], 1)
            self.assertEqual(self.request('/api/movies?search=does-not-exist')[2]['total'], 0)
            self.assertEqual(self.request('/api/movies?' + urlencode({'tag': '剧情', 'studio': '其他厂商'}))[2]['total'], 0)
            self.assertEqual(self.request('/api/stats')[2]['actors'], 1)
            key = self.app.store.get('api_key')
            self.assertEqual(self.request('/emby/Items?' + urlencode({'Ids': identity, 'Limit': 1, 'Fields': 'Path,MediaSources', 'ApiKey': key}))[2]['TotalRecordCount'], 1)
        for query in ('limit=101', 'limit=0', 'page=-1', 'page=bad', 'sort=unsafe', 'status=unsafe', 'folder=test'):
            with self.subTest(query=query):
                self.assertEqual(self.request('/api/movies?' + query)[0], 400)

    def test_facets_and_folder_tree_count_titles_instead_of_parts(self):
        root = str(self.root.resolve())
        for kind, name in (('actor', '示例演员'), ('studio', '示例工作室'), ('tag', '剧情')):
            data = self.request('/api/facets?' + urlencode({'kind': kind, 'search': name, 'limit': 1}))[2]
            self.assertEqual(data['total'], 1)
            self.assertEqual(data['items'][0]['name'], name)
            self.assertEqual(data['items'][0]['count'], 1)
        roots = self.request('/api/folders')[2]
        self.assertEqual(roots['items'][0]['count'], 1)
        children = self.request('/api/folders?' + urlencode({'root': root}))[2]
        self.assertEqual(len(children['items']), 1)
        self.assertEqual(children['items'][0], {'root': root, 'path': 'DEMO-001', 'name': 'DEMO-001', 'count': 1,
                                             'direct_count': 1, 'has_children': False})
        for path, count in (('', 1), ('DEMO-001', 1), ('DEMO-00', 0), ('../', 0)):
            self.assertEqual(self.request('/api/movies?' + urlencode({'root': root, 'folder': path}))[2]['total'], count)
        self.assertEqual(self.request('/api/facets?kind=unsafe')[0], 400)
        self.assertEqual(self.request('/api/folders?page=0')[0], 400)

    def test_combined_tag_and_directory_requests_are_bounded_and_read_only(self):
        root = str(self.root.resolve())
        query = urlencode({'actor': '示例演员', 'studio': '示例工作室', 'tag': ['收藏', '剧情'],
                           'root': root, 'folder': 'DEMO-001', 'recursive': '0'}, doseq=True)
        with patch.object(self.app.store, 'movies', side_effect=AssertionError('Full library read')):
            self.assertEqual(self.request('/api/movies?' + query)[2]['total'], 1)
            with patch('pathlib.Path.iterdir', side_effect=AssertionError('NAS directory read')):
                data = self.request('/api/folders?' + urlencode({'root': root, 'path': 'DEMO-001'}))[2]
            self.assertEqual([n['path'] for n in data['ancestors']], ['', 'DEMO-001'])
            self.assertEqual(data['selected']['direct_count'], 1)
        self.assertEqual(self.request('/api/movies?tag=' + '&tag='.join(['x']*21))[0], 400)
        self.assertEqual(self.request('/api/movies?recursive=bad')[0], 400)
        self.assertEqual(self.request('/api/folders?path=orphan')[0], 400)

    def test_incremental_scan_invalidates_sidecars_and_recovers_missing_resources(self):
        with patch('maxhub.scanner.nfo_metadata', side_effect=AssertionError('Unchanged NFO read')):
            self.scan()
        self.assertEqual(self.app.scanner.status['unchanged'], 2)
        self.assertFalse(self.app.scanner.status['errors'])
        self.scan(force=True)
        self.assertEqual(self.app.scanner.status['updated'], 2)
        nfo = self.folder / 'movie.nfo'
        nfo.write_text(NFO.replace('示例工作室', '新厂商'), encoding='utf-8')
        self.scan()
        self.assertEqual(self.app.scanner.status['updated'], 2)
        self.assertEqual(self.app.store.catalog.facets('studio')['items'][0]['name'], '新厂商')
        sample = self.folder / 'extrafanart' / '3.jpg'
        sample.write_bytes(b'new-artwork')
        self.scan()
        self.assertEqual(len(self.movie()['samples']), 3)
        resource = self.folder / 'DEMO-001-CD2.strm'
        content = resource.read_bytes()
        resource.unlink()
        self.scan()
        resource.write_bytes(content)
        self.scan()
        self.assertTrue(all(r['available'] for r in self.movie()['resources']))

    def test_catalog_migration_keeps_identity_state_and_does_not_scan_media(self):
        movie = self.movie()
        self.app.store.state(movie['id'], {'favorite': True, 'rating': 4})
        with self.app.store.connect() as db:
            for table in ('catalog', 'facets', 'folders'):
                db.execute('DROP TABLE ' + table)
            db.execute("DELETE FROM settings WHERE key='catalog_version'")
        with patch('maxhub.scanner.nfo_metadata', side_effect=AssertionError('Migration scanned NAS')):
            migrated = App(Path(self.temp.name) / 'data', [self.root])
        page = migrated.store.catalog.movies()
        self.assertEqual(page['items'][0]['id'], movie['id'])
        self.assertTrue(page['items'][0]['favorite'])
        self.assertEqual(page['items'][0]['rating'], 4)
        self.assertEqual(page['items'][0]['resource_count'], 2)
        self.assertEqual(migrated.store.catalog.facets('actor')['total'], 1)

    def test_thumbnails_revalidate_without_browser_sessions(self):
        poster = self.folder / 'poster.jpg'
        Image.new('RGB', (1600, 2400), (30, 120, 60)).save(poster)
        url = self.request('/api/movies')[2]['items'][0]['poster']
        status, headers, data = self.request(url)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/webp')
        self.assertEqual(headers['Cache-Control'], 'private, no-cache')
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, (360, 540))
        self.assertEqual(self.request(url, headers={'If-None-Match': headers['ETag']})[0], 304)
        Image.new('RGB', (1600, 2400), (180, 30, 60)).save(poster)
        os.utime(poster, ns=(poster.stat().st_atime_ns, poster.stat().st_mtime_ns + 1000000))
        status, changed, new_data = self.request(url, headers={'If-None-Match': headers['ETag']})
        self.assertEqual(status, 200)
        self.assertNotEqual(changed['ETag'], headers['ETag'])
        self.assertNotEqual(data, new_data)
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (2400, 1600)).save(poster, exif=exif)
        with Image.open(io.BytesIO(self.request(url)[2])) as image:
            self.assertEqual(image.size, (360, 540))
        self.assertEqual(self.request(url, method='HEAD')[0], 200)

    def test_litepan_lookup_reads_fresh_strm_without_exposing_internal_path(self):
        movie = self.movie()
        target = 'http://litepan:5211/api/strm/play/test-token/1/file/123/s/test-signature'
        (self.folder / 'DEMO-001-CD2.strm').write_text(target, encoding='utf-8')
        key = self.app.store.get('api_key')
        # Same lookup and auth shape used by LitePan redirectSTRMStream/fetchEmbyItem.
        data = self.request('/emby/Items?' + urlencode({'Ids': movie['id'], 'Limit': '1', 'Fields': 'Path,MediaSources', 'Recursive': 'true', 'ApiKey': key}))[2]
        sources = data['Items'][0]['MediaSources']
        self.assertEqual(sources[1]['Path'], target)
        self.assertEqual(sources[1]['Id'], movie['resources'][1]['id'])
        self.assertNotIn(str(self.root), json.dumps(data))

    def test_shared_part_artwork_uses_scraped_base_name(self):
        (self.folder / 'movie.nfo').write_text('<movie><num>DEMO-001</num><title>Shared artwork</title></movie>')
        (self.folder / 'poster.jpg').rename(self.folder / 'DEMO-001-poster.jpg')
        (self.folder / 'fanart.jpg').rename(self.folder / 'DEMO-001-fanart.jpg')
        self.scan()
        self.assertFalse(self.app.scanner.status['errors'])
        self.assertEqual(Path(self.movie()['poster']).name, 'DEMO-001-poster.jpg')
        self.assertEqual(Path(self.movie()['cover']).name, 'DEMO-001-fanart.jpg')

    def test_shared_artwork_can_be_requested_by_many_cards_concurrently(self):
        Image.new('RGB', (1600, 2400), (50, 80, 120)).save(self.folder / 'poster.jpg')
        url = self.request('/api/movies')[2]['items'][0]['poster']
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.request(url), range(16)))
        self.assertEqual([r[0] for r in responses], [200]*16)
        self.assertEqual(len({r[2] for r in responses}), 1)
        self.assertEqual(list(self.app.artwork.directory.glob('*.tmp')), [])

    def test_local_entity_pages_use_bounded_index_data_and_keep_resources_separate(self):
        with patch.object(self.app.store, 'movies', side_effect=AssertionError('Full library load')):
            with patch.object(self.app.store, 'movie', side_effect=AssertionError('Full metadata load')):
                status, _, actor = self.request('/api/entities?' + urlencode({'kind': 'actor', 'name': '示例演员'}))
                self.assertEqual(status, 200)
                self.assertEqual((actor['movie_count'], actor['resource_count'], actor['available_count']), (1, 2, 1))
                self.assertEqual(actor['first_year'], '2025')
                self.assertEqual(actor['last_year'], '2025')
                self.assertTrue(actor['thumb'].startswith('/api/assets/'))
                self.assertEqual(actor['related']['studios'][0]['name'], '示例工作室')
                status, _, studio = self.request('/api/entities?' + urlencode({'kind': 'studio', 'name': '示例工作室'}))
                self.assertEqual(status, 200)
                self.assertIsNone(studio['thumb'])
                self.assertEqual(studio['related']['actors'][0]['count'], 1)
                self.assertNotIn(str(self.root), json.dumps(studio))
        self.assertEqual(self.request('/api/entities?kind=tag&name=test')[0], 400)
        self.assertEqual(self.request('/api/entities?kind=actor')[0], 400)
        self.assertEqual(self.request('/api/entities?kind=actor&name=unknown')[0], 404)

    def test_detail_resources_have_relative_folders_and_gallery_has_small_thumbnails(self):
        detail = self.request('/api/movies/' + self.movie()['id'])[2]
        self.assertEqual([r['folder'] for r in detail['resources']], ['DEMO-001', 'DEMO-001'])
        self.assertNotIn('path', detail['resources'][0])
        Image.new('RGB', (1600, 900)).save(self.folder / 'extrafanart' / '2.jpg')
        status, headers, image = self.request(detail['samples'][0] + '?size=preview')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/webp')
        with Image.open(io.BytesIO(image)) as thumbnail:
            self.assertEqual(thumbnail.size, (320, 180))


if __name__ == '__main__':
    unittest.main()
