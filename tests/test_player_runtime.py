"""播放器运行边界、本地导入与历史兼容的行为回归。"""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from PIL import Image

from peach import settings_file
from peach.api import create_app
from peach.config import PeachSettings
from peach.player_library import process_library
from peach.repository import LedgerDatabase
from support.ledger import fresh_ledger
from support.web import route_client


class PlayerRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.db = fresh_ledger(self.root)
        self.settings = PeachSettings(configured=True, db_path=self.db, mdns_enabled=False,
            candidate_root=self.root / "generated", snapshot_root=self.root / "snapshots",
            cover_root=self.root / "covers", avatar_root=self.root / "avatars",
            logo_root=self.root / "logos", poster_root=self.root / "posters",
            timeline_root=self.root / "timeline", photo_root=self.root / "photos",
            transcode_root=self.root / "transcodes", stream_root=self.root / "streams",
            follow_state_root=self.root / "state", entry_links_root=self.root / "entry-links")

    def app(self):
        app = create_app(self.settings)
        self.addCleanup(app.state.http_transport.close)
        self.addCleanup(app.state.hls_plan_executor.shutdown, wait=False)
        return app

    def test_removed_features_have_no_http_entry_and_cannot_start_work(self):
        app = self.app()
        paths = ("/api/follow", "/api/follow/check", "/api/follow/resolve", "/api/feeds",
            "/api/feeds/check", "/api/downloads", "/api/downloads/postprocess", "/api/resources/search",
            "/api/jav/detail", "/api/jav/discoveries", "/api/scraping", "/api/scraping/cover",
            "/api/performer-scrape", "/api/configuration/downloads", "/api/configuration/push-discovery",
            "/api/configuration/indexers", "/api/inbox/clouddrive", "/api/clouddrive/inbox", "/api/taste/import",
            "/api/opencode-go/models", "/api/jav-browser", "/api/jav-browser/configuration", "/follow-stream", "/follow-cover",
            "/follow-image", "/follow-avatar", "/jav-preview/ABC-123/x", "/api/avatar-code-cover",
            "/api/avatar-choices", "/api/avatar-frame", "/api/avatar-pick", "/work-icon", "/site-mark")
        with route_client(app) as client:
            for path in paths:
                for method in ("GET", "POST"):
                    with self.subTest(path=path, method=method):
                        response = client.request(method, path, **({"json": {}} if method == "POST" else {}))
                        self.assertIn(response.status_code, (404, 405, 410))
        self.assertIsNone(app.state.web_contract.followups)

    def test_player_starts_without_optional_scraper_and_desktop_dependencies(self):
        probe = self.root / "probe.py"
        probe.write_text('''import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'cv2', 'numpy', 'apscheduler', 'browserexport', 'ahocorasick',
                'grpc', 'google', 'torznab', 'bencode2', 'pystray', 'zeroconf', 'watchdog',
                'sentry_sdk', 'resvg_py', 'curl_cffi', 'opencc', 'wordninja', 'seiso'}:
            raise ImportError('optional runtime dependency: ' + fullname)
sys.meta_path.insert(0, BlockOptional())
from peach.api import create_app
from peach.config import PeachSettings
from peach import cli, server
cli.build_parser()
app = create_app(PeachSettings(configured=False, mdns_enabled=False))
app.state.http_transport.close()
app.state.hls_plan_executor.shutdown(wait=False)
''', encoding="utf-8")
        result = subprocess.run([sys.executable, "-X", "utf8", str(probe)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_read_endpoints_remain_available(self):
        with route_client(self.app()) as client:
            for path in ("/healthz", "/api/items", "/api/entity/shapes", "/api/index?kind=performer",
                         "/api/library-scan", "/api/library-processing", "/api/tasks"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 200)

    def test_removed_pages_and_aliases_return_404(self):
        with route_client(self.app()) as client:
            for path in ("/follow", "/subscriptions", "/sources", "/resource-sync", "/scraping",
                         "/follow-manage", "/follow/item/1", "/posts/1", "/jav", "/jav/movie/ABC-123",
                         "/taste", "/downloads", "/settings/subscriptions", "/settings/downloads",
                         "/integrations/peach-jav.user.js", "/activity", "/diagnostics"):
                for method in ('GET', 'HEAD'):
                    with self.subTest(path=path, method=method):
                        self.assertEqual(client.request(method, path, follow_redirects=False).status_code, 404)

    def test_work_route_redirects_to_an_active_local_video_and_preserves_query(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for asset_id, medium, disposal in ((1, 'video', 'vanished'), (2, 'video', None),
                                               (3, 'video', None), (4, 'image', None)):
                connection.execute("INSERT INTO asset(id,location,path,name,medium,code,disposal) VALUES(?,?,?,?,?,?,?)",
                                   (asset_id, 'local', f'R:\\media\\{asset_id}.strm', f'{asset_id}.strm',
                                    medium, 'ABP-001', disposal))
        with patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("work route network request")), \
                route_client(self.app()) as client:
            for method in ('GET', 'HEAD'):
                response = client.request(method, '/works/abp001?tag=a%2Fb&tag=c&t=42', follow_redirects=False)
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response.headers['location'], '/assets/2?tag=a%2Fb&tag=c&t=42')

    def test_work_route_returns_404_when_no_active_local_video_matches(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO asset(id,location,path,name,medium,code,disposal) "
                               "VALUES(1,'local','R:\\media\\gone.strm','gone.strm','video','ABP-001','vanished')")
            connection.execute("INSERT INTO asset(id,location,path,name,medium,code,disposal) "
                               "VALUES(2,'local','R:\\media\\image.jpg','image.jpg','image','ABP-002',NULL)")
            connection.execute("INSERT INTO asset(id,location,path,name,medium,code,disposal) "
                               "VALUES(3,'local','','missing.strm','video','ABP-003',NULL)")
        with route_client(self.app()) as client:
            for code in ('ABP-001', 'ABP-002', 'ABP-003', 'SSIS-999', 'not-a-code'):
                for method in ('GET', 'HEAD'):
                    self.assertEqual(client.request(method, '/works/' + code).status_code, 404)

    def test_unconfigured_work_route_returns_404_without_creating_a_database(self):
        self.settings = replace(self.settings, configured=False, db_path=self.root / 'missing.db')
        with route_client(self.app()) as client:
            self.assertEqual(client.get('/works/ABP-001').status_code, 404)
        self.assertFalse(self.settings.db_path.exists())

    def test_startup_preserves_task_history_without_restoring_external_jobs(self):
        from peach.api import _start_ledger_services
        app = self.app()
        contract = app.state.web_contract
        with patch.object(contract.task_runs, "recover_interrupted", side_effect=AssertionError("task history write")), \
                patch("peach.web_job_recovery.restore", side_effect=AssertionError("online recovery")):
            self.assertTrue(_start_ledger_services(self.settings, contract, ()))

    def test_service_lifecycle_preserves_existing_task_rows(self):
        from fastapi.testclient import TestClient
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO task_run(task_key,trigger,status,mutex_key,pid,host,started_at,heartbeat_at) "
                               "VALUES('performer-scrape','manual','running','performer-scrape',0,'test','2000-01-01','2000-01-01')")
            before = connection.execute("SELECT * FROM task_run").fetchall()
        with patch("peach.mount_reachability.source_roots", return_value={}):
            app = self.app()
        with patch("httpx.Client.request", side_effect=AssertionError("startup network request")):
            with TestClient(app):
                self.assertTrue(app.state.ledger_background_ready)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT * FROM task_run").fetchall(), before)

    def test_authentication_and_playback_records_remain_available(self):
        self.settings = replace(self.settings, token="secret", access_path=self.root / "access.json")
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO asset(id,location,path,name,medium) VALUES(1,'local','R:\\test.mp4','test.mp4','video')")
        with route_client(self.app()) as client:
            self.assertEqual(client.get("/api/items").status_code, 401)
            self.assertEqual(client.post("/api/play", json={"id": 1}).status_code, 401)
            response = client.post("/login", content="token=secret&next=%2F",
                                   headers={"Content-Type": "application/x-www-form-urlencoded"}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(client.post("/api/play", json={"id": 1}).status_code, 200)
            self.assertEqual(client.post("/api/activity", json={"id": 1, "position": 20, "duration": 100, "delta": 4}).status_code, 200)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT play_count,play_seconds,leave_ratio FROM asset WHERE id=1").fetchone(), (1, 4, .2))

    def test_sample_images_only_use_existing_cache(self):
        app = self.app()
        with patch.object(app.state.sample_cache, "fetch", side_effect=AssertionError("network image")), \
                route_client(app) as client:
            self.assertEqual(client.get("/sample-image?code=ABC-123&n=1").status_code, 404)


class LocalImportTests(unittest.TestCase):
    def test_scan_preserves_old_missing_rows_and_reads_only_local_sidecars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            media = root / "media"
            media.mkdir()
            video = media / "ABC-123.strm"
            video.write_text("https://media.example.test/never-play.mp4", encoding="utf-8")
            video.with_suffix(".nfo").write_text("<movie><title>扫描导入</title><num>ABC-123</num></movie>", encoding="utf-8")
            db = fresh_ledger(root)
            ledger_root = str(media) if sys.platform == 'win32' else r'R:\media'
            missing_path = str(PureWindowsPath(ledger_root) / 'missing' / video.name)
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("INSERT INTO asset(id,location,path,name,medium,code,disposal,play_count) "
                                   "VALUES(1,'local',?,'ABC-123.strm','video','ABC-123','vanished',5)",
                                   (missing_path,))
                original = connection.execute("SELECT * FROM asset WHERE id=1").fetchone()
            config = replace(settings_file.PeachConfig(root, root / "config.toml"), present=True,
                             locations={"local": (ledger_root,)}, mounts={"local": (str(media),)})
            with patch("peach.settings_file.active", return_value=config), \
                    patch("httpx.Client.request", side_effect=AssertionError("scan network request")):
                result = process_library(config, db, root / "generated", root / "covers")
            self.assertEqual(result["issue_count"], 0, result)
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT * FROM asset WHERE id=1").fetchone(), original)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM asset").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT catalog_title FROM asset WHERE id<>1").fetchone()[0], "扫描导入")

    def test_nfo_and_art_import_is_offline_preserves_manual_fields_and_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            media = root / "media"
            media.mkdir()
            video = media / "ABC-123.strm"
            video.write_text("https://media.example.test/video.mp4", encoding="utf-8")
            nfo = media / "ABC-123.nfo"
            nfo.write_text("<movie><title>本地标题</title><num>ABC-123</num><studio>本地厂牌</studio>"
                           "<actor><name>本地演员</name></actor><tag>收藏分类</tag>"
                           "<thumb>https://example.test/never-fetch.jpg</thumb></movie>", encoding="utf-8")
            Image.new("RGB", (12, 16), "red").save(media / "ABC-123-poster.jpg")
            original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in media.iterdir()}
            db = fresh_ledger(root)
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("INSERT INTO asset(id,location,path,name,medium,catalog_title,field_owners,play_count) "
                                   "VALUES(1,'local',?,?,'video','手动标题',?,3)",
                                   (str(video), video.name, '{"catalog_title":"user:manual"}'))
            config = replace(settings_file.PeachConfig(root, root / "config.toml"),
                             present=True, locations={"local": (str(media),)})
            with patch("peach.player_library.translate_ledger_path", side_effect=Path), \
                    patch("httpx.Client.request", side_effect=AssertionError("network request")):
                result = process_library(config, db, root / "generated", root / "covers",
                                         stage="metadata", database=LedgerDatabase(db))
            self.assertEqual((result["status"], result["checked"], result["issue_count"]), ("complete", 1, 0))
            self.assertEqual((root / "covers" / "ABC-123.jpg").read_bytes(), (media / "ABC-123-poster.jpg").read_bytes())
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT catalog_title,studio,code,play_count FROM asset").fetchone(),
                                 ("手动标题", "本地厂牌", "ABC-123", 3))
                self.assertEqual(connection.execute("SELECT canonical_name FROM entity WHERE kind='performer'").fetchone(), ("本地演员",))
            self.assertEqual(original, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in media.iterdir()})

    def test_conflicting_nfo_does_not_change_asset_or_fetch_remote_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            video = root / "ABC-123.strm"
            video.write_text("https://media.example.test/video.mp4", encoding="utf-8")
            video.with_suffix(".nfo").write_text("<movie><title>不应导入</title><num>SSIS-001</num></movie>", encoding="utf-8")
            db = fresh_ledger(root)
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("INSERT INTO asset(location,path,name,medium) VALUES('local',?,?,'video')", (str(video), video.name))
            config = replace(settings_file.PeachConfig(root, root / "config.toml"), present=True,
                             locations={"local": (str(root),)})
            with patch("peach.player_library.translate_ledger_path", side_effect=Path):
                result = process_library(config, db, root / "generated", root / "covers", stage="metadata")
            self.assertEqual(result["issue_count"], 1, result)
            with closing(sqlite3.connect(db)) as connection:
                self.assertIsNone(connection.execute("SELECT catalog_title FROM asset").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
