"""横幅只读发现、影片配对与鉴权取图。"""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from PIL import Image

from peach import local_artwork
from peach.api import create_app
from peach.config import PeachSettings
from tests.support.ledger import fresh_ledger
from tests.support.web import route_client


class LocalArtworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.video = self.root / 'ABC-123.strm'
        self.video.write_text('https://media.example/test.mp4', encoding='utf-8')

    def picture(self, name):
        target = self.root / name
        Image.new('RGB', (320, 180), 'navy').save(target)
        return target

    def test_dedicated_artwork_wins_and_case_is_insensitive(self):
        self.picture('fanart.jpg')
        chosen = self.picture('ABC-123-FANART.JPG')
        self.assertEqual(local_artwork.backdrop(self.video), chosen)

    def test_shared_artwork_is_only_used_in_single_video_directory(self):
        shared = self.picture('fanart.jpg')
        self.assertEqual(local_artwork.backdrop(self.video), shared)
        (self.root / 'DEF-456.strm').write_text('https://media.example/other.mp4', encoding='utf-8')
        self.assertIsNone(local_artwork.backdrop(self.video))
        chosen = self.picture('ABC-123-banner.png')
        self.assertEqual(local_artwork.backdrop(self.video), chosen)

    def test_nfo_local_reference_is_supported_and_remote_or_escaping_references_are_ignored(self):
        chosen = self.picture('scene.png')
        nfo = self.video.with_suffix('.nfo')
        nfo.write_text('<movie><fanart><thumb>scene.png</thumb></fanart></movie>', encoding='utf-8')
        self.assertEqual(local_artwork.backdrop(self.video), chosen)
        for value in ('../outside.jpg', 'https://media.example/scene.jpg', 'scene.txt'):
            nfo.write_text(f'<movie><art><fanart>{value}</fanart></art></movie>', encoding='utf-8')
            self.assertIsNone(local_artwork.backdrop(self.video))
        nfo.write_text('<movie>', encoding='utf-8')
        fallback = self.picture('fanart.jpg')
        self.assertEqual(local_artwork.backdrop(self.video), fallback)

    def test_detail_and_image_api_use_authorized_media_and_revalidate_image(self):
        chosen = self.picture('ABC-123-fanart.jpg')
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.iterdir()}
        (self.root / 'data').mkdir()
        db = fresh_ledger(self.root / 'data')
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('INSERT INTO asset(location,path,name,medium) VALUES(?,?,?,?)',
                               ('local', str(self.video), self.video.name, 'video'))
            asset_id = connection.execute("SELECT id FROM asset WHERE name=?", (self.video.name,)).fetchone()[0]
        app = create_app(PeachSettings(db_path=db, configured=True, token='', allowed_media_roots=(self.root,)))
        with route_client(app) as client:
            self.assertTrue(client.get(f'/api/item?id={asset_id}').json()['has_backdrop'])
            response = client.get(f'/backdrop?id={asset_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, chosen.read_bytes())
            self.assertEqual(client.head(f'/backdrop?id={asset_id}').content, b'')
            self.assertEqual(client.get(f'/backdrop?id={asset_id}', headers={'If-None-Match': response.headers['etag']}).status_code, 304)
            self.assertEqual(client.get('/backdrop?id=999999').status_code, 404)
            app.state.settings = replace(app.state.settings, token='secret')
            self.assertEqual(client.get(f'/backdrop?id={asset_id}').status_code, 401)
        for name, state in before.items():
            path = self.root / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state)
        app = create_app(PeachSettings(db_path=db, configured=True, token='', allowed_media_roots=(self.root / 'denied',)))
        with route_client(app) as client:
            self.assertFalse(client.get(f'/api/item?id={asset_id}').json()['has_backdrop'])
            self.assertEqual(client.get(f'/backdrop?id={asset_id}').status_code, 404)
