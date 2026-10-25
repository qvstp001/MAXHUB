"""独立人物补全的任务边界；只使用临时账本与可控来源。"""
import contextlib
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from peach import web_performer_scrape as scrape
from peach import gfriends
from peach.performer_profiles import read_profile, write_profile
from peach.web_contract import WebContract
from peach.web_router import dispatch_api_get, dispatch_api_post
from support.ledger import fresh_ledger


class PerformerScrapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.db = fresh_ledger(self.root)
        self.contract = WebContract(self.db)
        self.addCleanup(self.contract.stop_background_jobs)
        with self.contract.database.write_transaction() as db:
            db.executemany("INSERT INTO entity(id,kind,canonical_name,normalized_name,created_at,updated_at) VALUES(?,?,?,?,'test','test')", [
                (1, 'performer', '示例甲', '示例甲'), (2, 'performer', '示例乙', '示例乙'),
                (3, 'studio', '示例社', '示例社'), (4, 'performer', '示例丙', '示例丙')])
            db.executemany("INSERT INTO asset(id,location,path,name,medium,code,rating,disposal) "
                           "VALUES(?,'local',?,?,'video','TEST-001',4,?)", [
                (1, str(self.root / 'one.strm'), 'one', None),
                (2, str(self.root / 'gone.strm'), 'gone', 'vanished')])
            db.executemany("INSERT INTO asset_entity(asset_id,entity_id,role,source) VALUES(?,?,'performer','test')",
                           [(1, 1), (1, 2), (2, 4)])
            db.execute("INSERT INTO asset_tag(asset_id,tag,source) VALUES(1,'已有标签','test')")
            db.execute("INSERT INTO activity_event(asset_id,kind,occurred_at,source,value_json) "
                       "VALUES(1,'played','test','test','{\"position\":120}')")
        self.index = mock.patch.object(gfriends, 'ensure_index', return_value=True)
        self.index.start()
        self.addCleanup(self.index.stop)

    def post(self, body):
        return dispatch_api_post(self.contract, '/api/performer-scrape', body)

    def finish(self):
        self.contract.performer_scrape_job.thread.join(10)
        state = dispatch_api_get(self.contract, '/api/performer-scrape', {})
        self.assertNotEqual(state['status'], 'running', state)
        return state

    def protected_rows(self):
        with self.contract.read_connection() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if row[0] in ('asset', 'activity_event', 'watch_queue', 'media_binding', 'profile')
                      or row[0].startswith('asset_')]
            return {name: sorted((tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')), key=repr) for name in tables}

    def test_single_backed_up_and_fills_profile_without_changing_films(self):
        media = self.root / 'one.strm'
        media.write_bytes(b'https://example.invalid/stream')
        before = self.protected_rows()
        def profile(contract, key, handle, *, fill_missing):
            self.assertTrue(fill_missing)
            backups = list(self.root.glob('ledger.pre-performer-scrape-*.db'))
            self.assertEqual(len(backups), 1)
            with contextlib.closing(sqlite3.connect(backups[0])) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT count(*) FROM performer_profile').fetchone()[0], 0)
            with contract.database.write_transaction() as db:
                write_profile(db, 1, {'height_cm': 160, 'birth_date': '1995-01-01'},
                              source='auto:test', source_url='https://example.invalid/person', fill_missing=True)
            return {'outcome': '档案已补全', 'sites': {}}
        with mock.patch.object(scrape.profiles, 'run', side_effect=profile), \
                mock.patch.object(scrape.avatar_followup, 'run', return_value={'outcome': '已有头像'}), \
                mock.patch.object(scrape.avatar_picker, 'installed_digest', return_value='manual'):
            self.post({'confirmed': True, 'entity_ids': [1, 1]})
            state = self.finish()
        self.assertEqual((state['checked'], state['profiles'], state['avatars'], state['failed']), (1, 1, 0, 0))
        self.assertEqual(before, self.protected_rows())
        self.assertEqual(media.read_bytes(), b'https://example.invalid/stream')

    def test_validation_rejects_unconfirmed_wrong_kind_and_bad_ids(self):
        for body in ({'entity_ids': [1]}, {'confirmed': True, 'entity_ids': [3]},
                     {'confirmed': True, 'entity_ids': [True]}, {'confirmed': True, 'entity_ids': []},
                     {'confirmed': True, 'all': True, 'entity_ids': [1]}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.post(body)
        self.assertEqual(dispatch_api_get(self.contract, '/api/performer-scrape', {}), {'status': 'idle'})

    def test_batch_uses_active_library_and_retry_only_incomplete_people(self):
        results = [dict(entity_id=i, name=f'示例{i}', profile=True, avatar=False,
                        retryable=i == 2, message='档案已取得') for i in (1, 2)]
        with mock.patch.object(scrape, '_collect', side_effect=results) as collect:
            self.post({'confirmed': True, 'all': True})
            state = self.finish()
            self.assertEqual([call.args[1] for call in collect.call_args_list], [1, 2])
        with mock.patch.object(scrape, '_collect', return_value={**results[1], 'retryable': False}) as collect:
            self.post({'action': 'retry', 'confirmed': True, 'job_id': state['job_id']})
            self.assertEqual(self.finish()['failed'], 0)
            self.assertEqual([call.args[1] for call in collect.call_args_list], [2])

    def test_stop_finishes_current_person_and_rejects_stale_controls(self):
        entered, release = threading.Event(), threading.Event()
        def collect(_contract, entity_id, _handle):
            entered.set()
            self.assertTrue(release.wait(5))
            return dict(entity_id=entity_id, name='示例', profile=False, avatar=False, retryable=False, message='已有资料')
        with mock.patch.object(scrape, '_collect', side_effect=collect) as collect:
            state = self.post({'confirmed': True, 'all': True})
            self.assertTrue(entered.wait(5))
            try:
                same = self.post({'confirmed': True, 'all': True})
                self.assertEqual(state['job_id'], same['job_id'])
                with self.assertRaises(ValueError):
                    self.post({'action': 'stop', 'job_id': 'stale'})
                self.post({'action': 'stop', 'job_id': state['job_id']})
            finally:
                release.set()
            end = self.finish()
            self.assertTrue(end['stopped'])
            self.assertEqual(end['checked'], 1)
            self.assertEqual(collect.call_count, 1)

    def test_avatar_phase_runs_after_profile_failure_and_marks_retry(self):
        with mock.patch.object(scrape.profiles, 'run', side_effect=OSError('offline')), \
                mock.patch.object(scrape.avatar_followup, 'run', return_value={'outcome': '已装上'}) as avatar, \
                mock.patch.object(scrape.avatar_picker, 'installed_digest', side_effect=[None, 'new']):
            self.post({'confirmed': True, 'entity_ids': [1]})
            state = self.finish()
        self.assertEqual(avatar.call_count, 1)
        self.assertEqual(state['avatars'], 1)
        self.assertEqual(state['retry_ids'], [1])
        self.assertEqual(state['profiles'], 0)

    def test_saved_progress_skips_completed_people(self):
        job = self.contract.performer_scrape_job
        with mock.patch.object(scrape, '_collect', return_value=dict(
                entity_id=2, name='示例乙', profile=False, avatar=True, retryable=False, message='头像已取得')) as collect:
            job.start(lambda identity: scrape._run(self.contract, identity), restart=True,
                      initial={'entity_ids': [1, 2], 'completed_ids': [1], 'retry_ids': [], 'results': [],
                               'checked': 1, 'total': 2, 'profiles': 1, 'avatars': 0, 'index_ready': True},
                      recovery={'confirmed': True, 'entity_ids': [1, 2]})
            end = self.finish()
        self.assertEqual([call.args[1] for call in collect.call_args_list], [2])
        self.assertEqual((end['checked'], end['profiles'], end['avatars']), (2, 1, 1))

    def test_fill_missing_preserves_held_fields_and_manual_profile(self):
        with self.contract.database.write_transaction() as db:
            write_profile(db, 1, {'height_cm': 159, 'tags': ['已有标签']}, source='auto:test', source_url='original')
            write_profile(db, 1, {'height_cm': 170, 'birth_date': '1992-01-01', 'tags': ['新标签']},
                          source='auto:test', source_url='test', fill_missing=True)
            person = read_profile(db, 1)
            self.assertEqual((person['height_cm'], person['birth_date'], person['tags']), (159, '1992-01-01', ['已有标签']))
            write_profile(db, 2, {'height_cm': 161}, source='manual', source_url='')
            before = read_profile(db, 2)
            self.assertFalse(write_profile(db, 2, {'birth_date': '1992-01-01'}, source='auto:test', source_url='test', fill_missing=True))
            self.assertEqual(read_profile(db, 2), before)

    def test_profile_parser_and_existing_avatar_protection_keep_films_unchanged(self):
        from tests.test_performer_profile_followup import MINNANO_PROFILE, MINNANO_URL
        before = self.protected_rows()
        pages = {key: mock.Mock() for key in (scrape.profiles.MINNANO, scrape.profiles.AVWIKIDB, scrape.profiles.JAVDB)}
        with mock.patch.object(scrape.profiles, 'open_sites', return_value=pages), \
                mock.patch.object(scrape.profiles.alias, 'minnano_profile_pages', return_value=(
                    [(MINNANO_URL, MINNANO_PROFILE.replace('美ノ嶋めぐり', '示例甲'))], '')), \
                mock.patch.object(scrape.profiles, '_visit_avwikidb', return_value=0), \
                mock.patch.object(scrape.profiles, '_visit_javdb'), \
                mock.patch.object(scrape.avatar_picker, 'installed_digest', return_value='manual'), \
                mock.patch.object(scrape.avatar_followup, '_installed_record', return_value={'user_selected': True}), \
                mock.patch.object(scrape.avatar_followup, '_installed_small', return_value=False), \
                mock.patch.object(scrape.avatar_followup.avatar_cover_face, 'installed_face_px', return_value=None):
            self.post({'confirmed': True, 'entity_ids': [1]})
            result = self.finish()
        self.assertEqual(result['profiles'], 1, result)
        self.assertEqual(result['avatars'], 0, result)
        with self.contract.read_connection() as db:
            self.assertEqual(read_profile(db, 1)['height_cm'], 156)
        self.assertEqual(self.protected_rows(), before)


class GfriendsRefreshTests(unittest.TestCase):
    def test_index_refresh_is_bounded_and_reuses_fresh_cache(self):
        from peach.http import HttpResponse
        body = json.dumps({'Content': {'1-source': {'示例.jpg': 'example.jpg'}}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with mock.patch('peach.http.HttpxTransport') as factory:
                factory.return_value.return_value = HttpResponse(200, {}, body)
                self.assertTrue(gfriends.ensure_index(cache))
                request = factory.return_value.call_args.args
                self.assertEqual(request[0].method, 'GET')
                self.assertEqual(request[1:], (60, 32 * 1024 * 1024))
                self.assertEqual((cache / gfriends.INDEX_NAME).read_bytes(), body)
                self.assertTrue(gfriends.ensure_index(cache))
                self.assertEqual(factory.call_count, 1)

    def test_unavailable_refresh_keeps_cache(self):
        from httpx import ConnectError
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            held = cache / gfriends.INDEX_NAME
            held.write_bytes(b'old-cache')
            with mock.patch('peach.http.HttpxTransport') as transport:
                transport.return_value.side_effect = ConnectError('offline')
                self.assertFalse(gfriends.ensure_index(cache))
                transport.return_value.close.assert_called_once()
            self.assertEqual(held.read_bytes(), b'old-cache')
