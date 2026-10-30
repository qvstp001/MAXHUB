"""Small, rebuildable browse index. Source metadata and personal state stay in Store."""
import json
from pathlib import Path


def index_movie(db, movie_id, metadata):
    card = {key: metadata[key] for key in
            ('code', 'title', 'date', 'year', 'score', 'studio', 'poster', 'cover')}
    card['actors'] = [{'name': a['name']} for a in metadata['actors'][:2]]
    search = '\n'.join(str(metadata.get(k, '')) for k in ('code', 'title', 'studio', 'series'))
    search += '\n' + '\n'.join(metadata['tags'] + [a['name'] for a in metadata['actors']])
    db.execute('INSERT OR REPLACE INTO catalog(movie_id,card,search,code,date,score,title,added) '
               'VALUES (?,?,?,?,?,?,?,(SELECT added FROM movies WHERE id=?))',
               (movie_id, json.dumps(card, ensure_ascii=False), search.casefold(),
                metadata['code'], metadata['date'] or metadata['year'], metadata['score'], metadata['title'], movie_id))
    db.execute('DELETE FROM facets WHERE movie_id=?', (movie_id,))
    rows = [('actor', a['name'], i if a.get('thumb') else None) for i, a in enumerate(metadata['actors'])]
    rows += [('tag', t, None) for t in metadata['tags']]
    rows += [(k, metadata[k], None) for k in ('studio', 'series') if metadata[k]]
    db.executemany('INSERT OR IGNORE INTO facets VALUES (?,?,?,?)',
                   [(movie_id, kind, name, thumb) for kind, name, thumb in rows])


def index_resource(db, resource_id, root, path):
    folder = Path(path).relative_to(Path(root)).parent
    db.execute('DELETE FROM folders WHERE resource_id=?', (resource_id,))
    rows = []
    while True:
        value = '' if folder == Path('.') else folder.as_posix()
        parent = None if not value else ('' if folder.parent == Path('.') else folder.parent.as_posix())
        rows.append((resource_id, str(root), value, parent, int(not rows)))
        if not value:
            break
        folder = folder.parent
    db.executemany('INSERT INTO folders(resource_id,root,path,parent,direct) VALUES (?,?,?,?,?)', rows)


class Catalog:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS catalog (
                    movie_id TEXT PRIMARY KEY, card TEXT NOT NULL, search TEXT NOT NULL,
                    code TEXT NOT NULL, date TEXT NOT NULL, score REAL NOT NULL, title TEXT NOT NULL,
                    added REAL NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS catalog_code ON catalog(code COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS catalog_date ON catalog(date DESC);
                CREATE INDEX IF NOT EXISTS catalog_score ON catalog(score DESC);
                CREATE TABLE IF NOT EXISTS facets (
                    movie_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, thumb INTEGER,
                    PRIMARY KEY (movie_id,kind,name));
                CREATE INDEX IF NOT EXISTS facets_lookup ON facets(kind,name,movie_id);
                CREATE TABLE IF NOT EXISTS folders (
                    resource_id TEXT NOT NULL, root TEXT NOT NULL, path TEXT NOT NULL, parent TEXT,
                    direct INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (resource_id,path));
                CREATE INDEX IF NOT EXISTS folders_lookup ON folders(root,path,resource_id);
                CREATE INDEX IF NOT EXISTS folders_children ON folders(root,parent,path);
            ''')
            if 'direct' not in {r['name'] for r in db.execute('PRAGMA table_info(folders)')}:
                db.execute('ALTER TABLE folders ADD COLUMN direct INTEGER NOT NULL DEFAULT 0')
                for row in db.execute('SELECT id,root,path FROM resources').fetchall():
                    index_resource(db, row['id'], row['root'], row['path'])
            if 'added' not in {r['name'] for r in db.execute('PRAGMA table_info(catalog)')}:
                db.execute('ALTER TABLE catalog ADD COLUMN added REAL NOT NULL DEFAULT 0')
                db.execute('UPDATE catalog SET added=(SELECT added FROM movies WHERE id=catalog.movie_id)')
            db.execute('CREATE INDEX IF NOT EXISTS catalog_added ON catalog(added DESC,movie_id)')
            # Migrate once, without scanning the NAS or changing identities and user state.
            if not db.execute("SELECT 1 FROM settings WHERE key='catalog_version'").fetchone():
                for row in db.execute('SELECT id,metadata FROM movies').fetchall():
                    index_movie(db, row['id'], json.loads(row['metadata']))
                for row in db.execute('SELECT id,root,path FROM resources').fetchall():
                    index_resource(db, row['id'], row['root'], row['path'])
                db.execute("INSERT INTO settings VALUES ('catalog_version','1')")

    def movies(self, *, page=1, limit=60, search='', sort='added', status='', favorite=False,
               actor='', tag='', studio='', series='', root='', folder='', recursive=True):
        if page < 1 or not 1 <= limit <= 100:
            raise ValueError('页码至少为 1，每页数量为 1–100')
        ordering = {'added': 'c.added DESC', 'title': 'c.code COLLATE NOCASE, c.title COLLATE NOCASE',
                    'date': 'c.date DESC', 'score': 'c.score DESC'}
        if sort not in ordering or status not in ('', 'watched', 'unwatched', 'missing'):
            raise ValueError('无效的排序或观看筛选')
        if type(recursive) is not bool:
            raise ValueError('目录递归选项必须为布尔值')
        tags = [tag] if isinstance(tag, str) else tag
        if not isinstance(tags, (list, tuple)) or len(tags) > 20 or any(not isinstance(t, str) for t in tags):
            raise ValueError('一次最多选择 20 个影片标签')
        clauses = ['EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)']
        params = []
        if search.strip():
            clauses.append('instr(c.search,?)>0')
            params.append(search.strip().casefold())
        if favorite:
            clauses.append('s.favorite=1')
        if status in ('watched', 'unwatched'):
            clauses.append('coalesce(s.watched,0)=?')
            params.append(int(status == 'watched'))
        if status == 'missing':
            clauses.append('NOT EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id AND r.available=1)')
        for kind, value in [('actor', actor), ('studio', studio), ('series', series),
                            *(('tag', value) for value in dict.fromkeys(tags))]:
            if value:
                clauses.append('EXISTS (SELECT 1 FROM facets f WHERE f.movie_id=c.movie_id AND f.kind=? AND f.name=?)')
                params += [kind, value]
        if folder and not root:
            raise ValueError('文件夹筛选需要指定媒体来源')
        if root:
            clauses.append('EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id AND EXISTS '
                           '(SELECT 1 FROM folders f WHERE f.resource_id=r.id AND f.root=? AND f.path=?'
                           + ('' if recursive else ' AND f.direct=1') + '))')
            params += [root, folder]
        source = (' FROM catalog c LEFT JOIN user_state s ON s.movie_id=c.movie_id WHERE ' + ' AND '.join(clauses))
        with self.store.connect() as db:
            # A read snapshot keeps total and page consistent while a scan writes.
            db.execute('BEGIN')
            total = db.execute('SELECT count(*)' + source, params).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            rows = db.execute('SELECT c.card,c.movie_id id,c.added,s.favorite,s.watched,s.rating,'
                              '(SELECT count(*) FROM resources r WHERE r.movie_id=c.movie_id) resource_count,'
                              'EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id AND r.available=1) available'
                              + source + ' ORDER BY ' + ordering[sort] + ',c.movie_id LIMIT ? OFFSET ?',
                              [*params, limit, (page - 1) * limit]).fetchall()
        items = []
        for row in rows:
            item = json.loads(row['card'])
            prefix = '/api/assets/' + row['id']
            item.update(id=row['id'], added=row['added'], favorite=bool(row['favorite']),
                        watched=bool(row['watched']), rating=row['rating'] or 0,
                        resource_count=row['resource_count'], available=bool(row['available']),
                        poster=prefix + '/poster?size=card' if item['poster'] else None,
                        cover=prefix + '/cover?size=card' if item['cover'] else None)
            items.append(item)
        return dict(items=items, total=total, page=page, limit=limit)

    def facets(self, kind, page=1, limit=100, search=''):
        if kind not in ('actor', 'tag', 'studio', 'series') or page < 1 or not 1 <= limit <= 100:
            raise ValueError('无效的字段或分页参数')
        with self.store.connect() as db:
            db.create_function('casefold', 1, str.casefold, deterministic=True)
            db.execute('BEGIN')
            source = (' FROM facets f WHERE f.kind=? AND instr(casefold(f.name),?)>0 AND EXISTS '
                      '(SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id)')
            params = (kind, search.strip().casefold())
            total = db.execute('SELECT count(DISTINCT f.name)' + source, params).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            rows = db.execute('SELECT f.name,count(*) count,'
                              "min(CASE WHEN f.thumb IS NOT NULL THEN '/api/assets/' || f.movie_id || '/actor/' || f.thumb || '?size=avatar' END) thumb "
                              + source + ' GROUP BY f.name ORDER BY count DESC,f.name LIMIT ? OFFSET ?',
                              (*params, limit, (page-1)*limit)).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, page=page, limit=limit)

    def folders(self, root='', path='', page=1, limit=100, search=''):
        if page < 1 or not 1 <= limit <= 100:
            raise ValueError('无效的文件夹分页参数')
        if path and not root:
            raise ValueError('目录路径需要指定媒体来源')
        with self.store.connect() as db:
            db.create_function('casefold', 1, str.casefold, deterministic=True)
            db.execute('BEGIN')
            select = ('SELECT f.root,f.path,count(DISTINCT r.movie_id) count,'
                      'count(DISTINCT CASE WHEN f.direct=1 THEN r.movie_id END) direct_count,'
                      'EXISTS (SELECT 1 FROM folders child WHERE child.root=f.root AND child.parent=f.path) has_children '
                      'FROM folders f JOIN resources r ON r.id=f.resource_id WHERE ')
            if search.strip():
                condition = "f.path<>'' AND instr(casefold(f.path),?)>0"
                params = [search.strip().casefold()]
                if root:
                    condition += ' AND f.root=?'
                    params.append(root)
            elif not root:
                condition, params = "f.path=''", []
            else:
                condition, params = 'f.root=? AND f.parent=?', [root, path]
            source = select + condition + ' GROUP BY f.root,f.path'
            total = db.execute('SELECT count(*) FROM (' + source + ')', params).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            rows = db.execute(source + ' ORDER BY f.root,f.path LIMIT ? OFFSET ?', (*params, limit, (page-1)*limit)).fetchall()
            ancestors = []
            if root:
                parts = path.split('/') if path else []
                paths = [''] + ['/'.join(parts[:i]) for i in range(1, len(parts)+1)]
                if len(paths) > 128:
                    raise ValueError('目录层数过多')
                nodes = db.execute(select + 'f.root=? AND f.path IN (' + ','.join('?' for _ in paths)
                                   + ') GROUP BY f.root,f.path', [root, *paths]).fetchall()
                by_path = {r['path']: self.folder_node(r) for r in nodes}
                if path in by_path:
                    ancestors = [by_path[p] for p in paths if p in by_path]
        return dict(items=[self.folder_node(r) for r in rows], total=total, page=page, limit=limit,
                    ancestors=ancestors, selected=ancestors[-1] if ancestors else None)

    def entity(self, kind, name):
        """本地身份页的聚合资料，不读取完整影片元数据或媒体目录。"""
        if kind not in ('actor', 'studio') or not isinstance(name, str) or not name.strip():
            raise ValueError('请选择有效的演员或厂商')
        name = name.strip()
        scope = (' FROM facets focus JOIN catalog c ON c.movie_id=focus.movie_id '
                 'WHERE focus.kind=? AND focus.name=? AND EXISTS '
                 '(SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)')
        with self.store.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT count(*) movie_count,'
                'coalesce(sum(EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id AND r.available=1)),0) available_count,'
                'coalesce(sum((SELECT count(*) FROM resources r WHERE r.movie_id=c.movie_id)),0) resource_count,'
                "min(CASE WHEN c.date GLOB '[12][0-9][0-9][0-9]*' THEN substr(c.date,1,4) END) first_year,"
                "max(CASE WHEN c.date GLOB '[12][0-9][0-9][0-9]*' THEN substr(c.date,1,4) END) last_year,"
                "min(CASE WHEN focus.thumb IS NOT NULL THEN '/api/assets/' || focus.movie_id || '/actor/' || focus.thumb || '?size=avatar' END) thumb"
                + scope, (kind, name)).fetchone()
            if not row['movie_count']:
                return None
            result = dict(row)
            related = {'studios': [], 'actors': [], 'tags': []}
            for target, key in (('studio', 'studios'), ('actor', 'actors'), ('tag', 'tags')):
                if target == kind:
                    continue
                rows = db.execute('SELECT f.name,count(*) count,'
                    "min(CASE WHEN f.kind='actor' AND f.thumb IS NOT NULL THEN '/api/assets/' || f.movie_id || '/actor/' || f.thumb || '?size=avatar' END) thumb "
                    'FROM facets f JOIN facets focus ON focus.movie_id=f.movie_id '
                    'WHERE focus.kind=? AND focus.name=? AND f.kind=? AND EXISTS '
                    '(SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id) '
                    'GROUP BY f.name ORDER BY count DESC,f.name LIMIT 8', (kind, name, target)).fetchall()
                related[key] = [dict(r) for r in rows]
        return dict(kind=kind, name=name, missing_count=result['movie_count']-result['available_count'],
                    related=related, **result)

    @staticmethod
    def folder_node(row):
        item = dict(row)
        item['name'] = item['path'].rsplit('/', 1)[-1] if item['path'] else item['root']
        item['has_children'] = bool(item['has_children'])
        return item

    def stats(self):
        with self.store.connect() as db:
            row = db.execute('SELECT count(*) total,coalesce(sum(coalesce(s.favorite,0)),0) favorites '
                             'FROM catalog c LEFT JOIN user_state s ON s.movie_id=c.movie_id '
                             'WHERE EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)').fetchone()
            actors = db.execute("SELECT count(DISTINCT f.name) FROM facets f WHERE f.kind='actor' AND EXISTS "
                                '(SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id)').fetchone()[0]
        return {**dict(row), 'actors': actors}
