import json
import tempfile
import unittest
from pathlib import Path

from maxhub.catalog import index_movie, index_resource
from maxhub.scanner import nfo_metadata
from maxhub.store import Store


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parent.parent / '.test-data'
        self.workspace.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.workspace)
        self.root = Path(self.temp.name) / 'media'
        self.store = Store(Path(self.temp.name) / 'data')
        with self.store.connect() as db:
            for i in range(127):
                meta = nfo_metadata(None, self.root, f'TEST-{i:03}', [self.root / 'placeholder.strm'])
                meta.update(title=f'影片 {i:03}', studio=f'厂商 {i % 3}', tags=['共有', f'标签 {i:03}'],
                            actors=[{'name': f'演员 {i:03}', 'thumb': None}, {'name': '共同演员', 'thumb': None}])
                if i == 0:
                    meta['title'] = 'Straße 100%'
                movie_id = f'{i:032x}'
                db.execute('INSERT INTO movies VALUES (?,?,?)', (movie_id, json.dumps(meta), i))
                index_movie(db, movie_id, meta)
                path = self.root / ('a' if i % 2 else 'ab') / f'{i:03}.strm'
                db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)',
                           (movie_id, movie_id, str(self.root), str(path), 'https://example.test/movie', 1, '', 'test'))
                index_resource(db, movie_id, self.root, path)

    def tearDown(self):
        if not Path(self.temp.name).resolve().is_relative_to(self.workspace):
            raise RuntimeError('Unexpected test cleanup path')
        self.temp.cleanup()

    def test_real_page_boundaries_stable_sort_and_out_of_range_clamp(self):
        pages = [self.store.catalog.movies(page=p) for p in (1, 2, 3)]
        self.assertEqual([len(p['items']) for p in pages], [60, 60, 7])
        self.assertEqual([p['total'] for p in pages], [127]*3)
        ids = [m['id'] for p in pages for m in p['items']]
        self.assertEqual(len(set(ids)), 127)
        self.assertEqual(ids[0], f'{126:032x}')
        self.assertEqual(self.store.catalog.movies(page=999)['page'], 3)
        self.assertEqual(self.store.catalog.movies(sort='title')['items'][0]['code'], 'TEST-000')

    def test_exact_folder_selection_unicode_search_and_live_state(self):
        self.assertEqual(self.store.catalog.movies(root=str(self.root), folder='a')['total'], 63)
        self.assertEqual(self.store.catalog.movies(root=str(self.root), folder='ab')['total'], 64)
        self.assertEqual(self.store.catalog.movies(root=str(self.root))['total'], 127)
        self.assertEqual(self.store.catalog.movies(search='STRASSE')['total'], 1)
        self.assertEqual(self.store.catalog.movies(search='100%')['total'], 1)
        self.assertEqual(self.store.catalog.movies(search="' OR 1=1 --")['total'], 0)
        self.assertEqual(self.store.catalog.movies(studio='厂商 0', tag='共有')['total'], 43)
        identity = f'{10:032x}'
        self.store.state(identity, {'favorite': True, 'watched': True})
        self.assertEqual(self.store.catalog.movies(favorite=True)['items'][0]['id'], identity)
        self.assertEqual(self.store.catalog.movies(status='unwatched')['total'], 126)
        with self.store.connect() as db:
            db.execute('UPDATE resources SET available=0 WHERE movie_id=?', (identity,))
        self.assertEqual(self.store.catalog.movies(status='missing')['items'][0]['id'], identity)

    def test_facets_are_paginated_and_shared_actor_counts_all_titles(self):
        first = self.store.catalog.facets('actor', limit=100)
        second = self.store.catalog.facets('actor', page=2, limit=100)
        self.assertEqual(first['total'], 128)
        self.assertEqual(len(second['items']), 28)
        self.assertEqual(first['items'][0]['name'], '共同演员')
        self.assertEqual(first['items'][0]['count'], 127)
        self.assertEqual(self.store.catalog.facets('actor', search='演员 126')['total'], 1)
        folders = self.store.catalog.folders(root=str(self.root), limit=1)
        self.assertEqual(folders['total'], 2)
        self.assertEqual(folders['items'][0]['path'], 'a')
        self.assertEqual(self.store.catalog.folders(root=str(self.root), page=2, limit=1)['items'][0]['path'], 'ab')

    def move_resource(self, number, relative):
        identity = f'{number:032x}'
        path = self.root / relative
        with self.store.connect() as db:
            db.execute('UPDATE resources SET path=? WHERE id=?', (str(path), identity))
            index_resource(db, identity, self.root, path)

    def test_nested_tree_exact_scope_ancestors_and_distinct_title_counts(self):
        self.move_resource(0, '片库/厂商甲/000.strm')
        self.move_resource(1, '片库/厂商甲/系列/001.strm')
        self.move_resource(2, '片库/厂商甲乙/002.strm')
        with self.store.connect() as db:
            path = self.root / '片库/厂商甲/系列/000-CD2.strm'
            db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)',
                       ('part-two', f'{0:032x}', str(self.root), str(path), 'https://example.test/part2', 1, '', 'test'))
            index_resource(db, 'part-two', self.root, path)
        recursive = self.store.catalog.movies(root=str(self.root), folder='片库/厂商甲')
        direct = self.store.catalog.movies(root=str(self.root), folder='片库/厂商甲', recursive=False)
        self.assertEqual(recursive['total'], 2)
        self.assertEqual(direct['total'], 1)
        self.assertEqual(direct['items'][0]['id'], f'{0:032x}')
        self.assertEqual(self.store.catalog.movies(root=str(self.root), folder='片库/厂商甲乙')['total'], 1)
        branch = self.store.catalog.folders(root=str(self.root), path='片库/厂商甲')
        self.assertEqual([n['path'] for n in branch['ancestors']], ['', '片库', '片库/厂商甲'])
        self.assertEqual(branch['selected']['count'], 2)
        self.assertEqual(branch['selected']['direct_count'], 1)
        self.assertTrue(branch['selected']['has_children'])
        self.assertEqual(branch['items'][0]['name'], '系列')
        self.assertEqual(branch['items'][0]['count'], 2)
        leaf = self.store.catalog.folders(root=str(self.root), path='片库/厂商甲/系列')
        self.assertFalse(leaf['selected']['has_children'])
        self.assertEqual(leaf['items'], [])
        self.assertIsNone(self.store.catalog.folders(root=str(self.root), path='不存在')['selected'])

    def test_multiple_tags_intersect_with_actor_studio_keyword_and_directory(self):
        query = dict(actor='共同演员', studio='厂商 0', tag=['共有', '标签 000'], search='STRASSE',
                     root=str(self.root), folder='ab', recursive=False)
        self.assertEqual(self.store.catalog.movies(**query)['total'], 1)
        query['tag'] = ['标签 000', '标签 001']
        self.assertEqual(self.store.catalog.movies(**query)['total'], 0)
        query['tag'] = ['共有', '共有']
        self.assertEqual(self.store.catalog.movies(**query)['total'], 1)
        with self.assertRaises(ValueError):
            self.store.catalog.movies(tag=['x']*21)

    def test_folder_search_is_paginated_and_root_scoped(self):
        self.move_resource(0, 'Studio/第一层/000.strm')
        self.move_resource(1, 'Studio/第二层/001.strm')
        first = self.store.catalog.folders(search='STUDIO', limit=1)
        self.assertEqual(first['total'], 3)
        self.assertEqual(first['items'][0]['path'], 'Studio')
        second = self.store.catalog.folders(search='STUDIO', limit=1, page=2)
        self.assertNotEqual(first['items'][0]['path'], second['items'][0]['path'])
        self.assertEqual(self.store.catalog.folders(root='other-root', search='STUDIO')['total'], 0)
        self.assertEqual(self.store.catalog.folders(search='不存在')['items'], [])

    def test_legacy_folder_index_migrates_without_scanning_sources(self):
        self.store.state(f'{0:032x}', {'favorite': True})
        with self.store.connect() as db:
            old_rows = db.execute('SELECT resource_id,root,path,parent FROM folders').fetchall()
            db.execute('DROP TABLE folders')
            db.execute('CREATE TABLE folders(resource_id TEXT,root TEXT,path TEXT,parent TEXT,PRIMARY KEY(resource_id,path))')
            db.executemany('INSERT INTO folders VALUES (?,?,?,?)', [tuple(r) for r in old_rows])
        migrated = Store(Path(self.temp.name) / 'data')
        direct = migrated.catalog.movies(root=str(self.root), folder='ab', recursive=False)
        self.assertEqual(direct['total'], 64)
        self.assertEqual(migrated.catalog.folders(root=str(self.root), path='ab')['selected']['direct_count'], 64)
        self.assertTrue(migrated.movie(f'{0:032x}')['favorite'])

    def test_entity_statistics_deduplicate_parts_and_bound_associations(self):
        with self.store.connect() as db:
            db.execute('UPDATE resources SET available=0 WHERE id IN (?,?)', (f'{0:032x}', f'{1:032x}'))
            db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)',
                       ('another-version', f'{0:032x}', str(self.root), str(self.root / 'alternate.strm'),
                        'https://example.test/another', 1, '', 'test'))
            for number, date in ((0, '2020-01-01'), (1, '2025-06-12')):
                db.execute('UPDATE catalog SET date=? WHERE movie_id=?', (date, f'{number:032x}'))
        actor = self.store.catalog.entity('actor', '共同演员')
        self.assertEqual(actor['movie_count'], 127)
        self.assertEqual(actor['resource_count'], 128)
        self.assertEqual(actor['available_count'], 126)
        self.assertEqual(actor['missing_count'], 1)
        self.assertEqual((actor['first_year'], actor['last_year']), ('2020', '2025'))
        self.assertEqual(actor['related']['tags'][0]['name'], '共有')
        self.assertEqual(actor['related']['tags'][0]['count'], 127)
        self.assertEqual(len(actor['related']['tags']), 8)
        self.assertEqual(len(actor['related']['studios']), 3)
        studio = self.store.catalog.entity('studio', '厂商 0')
        self.assertEqual(studio['movie_count'], 43)
        self.assertEqual(studio['related']['actors'][0]['name'], '共同演员')
        self.assertEqual(studio['related']['actors'][0]['count'], 43)
        self.assertIsNone(self.store.catalog.entity('actor', "' OR 1=1 --"))
        with self.assertRaises(ValueError):
            self.store.catalog.entity('invalid', 'test')
