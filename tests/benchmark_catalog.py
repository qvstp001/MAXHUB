"""Synthetic browse benchmark; no NAS, cloud URLs, or user data are accessed."""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from maxhub.catalog import index_movie, index_resource
from maxhub.scanner import nfo_metadata
from maxhub.server import App


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    workspace = Path(__file__).resolve().parent.parent / '.test-data'
    workspace.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        root = Path(directory) / 'media'
        app = App(Path(directory) / 'data', [root])
        template = nfo_metadata(None, root, 'BENCH-00000', [root / 'placeholder.strm'])
        with app.store.connect() as db:
            for i in range(count):
                meta = {**template, 'code': f'BENCH-{i:05}', 'title': f'BENCH-{i:05}'}
                meta.update(plot='本地简介与元数据。' * 160, studio=f'厂商 {i % 20}',
                            tags=[f'标签 {i % 50}'], actors=[{'name': f'演员 {i % 1000}', 'thumb': None}],
                            samples=[str(root / f'sample-{n}.jpg') for n in range(20)])
                movie_id = f'{i:032x}'
                db.execute('INSERT INTO movies VALUES (?,?,?)', (movie_id, json.dumps(meta, ensure_ascii=False), i))
                index_movie(db, movie_id, meta)
                path = root / f'folder-{i % 50}' / f'{i}.strm'
                db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)',
                           (movie_id, movie_id, str(root), str(path), 'https://example.test/unused', 1, '', 'test'))
                index_resource(db, movie_id, root, path)
        timings = []
        for _ in range(5):
            start = time.perf_counter()
            page = app.store.catalog.movies()
            payload = json.dumps(page, ensure_ascii=False).encode()
            timings.append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        previous = json.dumps({'items': [app.public_movie(m) for m in app.store.movies()]}, ensure_ascii=False).encode()
        full_ms = (time.perf_counter()-start)*1000
        start = time.perf_counter()
        filtered = app.store.catalog.movies(studio='厂商 3', tag='标签 3')
        filter_ms = (time.perf_counter()-start)*1000
        print(json.dumps({'synthetic_titles': count, 'page_titles': len(page['items']),
                          'page_bytes': len(payload), 'page_median_ms': round(statistics.median(timings), 2),
                          'previous_all_titles_bytes': len(previous), 'previous_all_titles_ms': round(full_ms, 2),
                          'combined_filter_total': filtered['total'], 'combined_filter_ms': round(filter_ms, 2)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
