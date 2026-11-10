"""Personal collections stored independently of the rebuildable media index."""
import secrets
import sqlite3
import time


class CollectionNotFound(LookupError):
    pass


class Collections:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS favorite_actors (
                    name TEXT PRIMARY KEY, added REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS custom_lists (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, added REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS list_movies (
                    list_id TEXT NOT NULL REFERENCES custom_lists(id) ON DELETE CASCADE,
                    movie_id TEXT NOT NULL, added REAL NOT NULL,
                    PRIMARY KEY (list_id,movie_id));
                CREATE INDEX IF NOT EXISTS list_movies_movie ON list_movies(movie_id,list_id);
            ''')

    @staticmethod
    def name(value, maximum):
        if (not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum
                or any(ord(c) < 32 for c in value)):
            raise ValueError(f'名称须为 1–{maximum} 个字符，不能包含控制字符')
        return value.strip()

    @staticmethod
    def pagination(page, limit):
        if page < 1 or not 1 <= limit <= 100:
            raise ValueError('页码至少为 1，每页数量为 1–100')

    def favorite_actor(self, name, favorite):
        name = self.name(name, 200)
        if type(favorite) is not bool:
            raise ValueError('favorite 必须为布尔值')
        with self.store.connect() as db:
            if favorite:
                if not db.execute("SELECT 1 FROM facets f WHERE kind='actor' AND name=? AND EXISTS "
                                  '(SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id)', (name,)).fetchone():
                    raise CollectionNotFound('演员不存在')
                db.execute('INSERT OR IGNORE INTO favorite_actors VALUES (?,?)', (name, time.time()))
            else:
                db.execute('DELETE FROM favorite_actors WHERE name=?', (name,))
        return dict(name=name, favorite=favorite)

    def is_favorite_actor(self, name):
        with self.store.connect() as db:
            return bool(db.execute('SELECT 1 FROM favorite_actors WHERE name=?', (name,)).fetchone())

    def actors(self, page=1, limit=60, search=''):
        self.pagination(page, limit)
        with self.store.connect() as db:
            db.create_function('casefold', 1, str.casefold, deterministic=True)
            db.execute('BEGIN')
            source = ' FROM favorite_actors a WHERE instr(casefold(a.name),?)>0'
            params = [search.strip().casefold()]
            total = db.execute('SELECT count(*)' + source, params).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            rows = db.execute('SELECT a.name,(SELECT count(*) FROM facets f WHERE f.kind=\'actor\' '
                              'AND f.name=a.name AND EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id)) count,'
                              "(SELECT min('/api/assets/' || f.movie_id || '/actor/' || f.thumb || '?size=avatar') "
                              "FROM facets f WHERE f.kind='actor' AND f.name=a.name AND f.thumb IS NOT NULL "
                              'AND EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=f.movie_id)) thumb'
                              + source + ' ORDER BY a.added DESC,a.name LIMIT ? OFFSET ?',
                              [*params, limit, (page - 1) * limit]).fetchall()
        return dict(items=[dict(r) for r in rows], total=total, page=page, limit=limit)

    def lists(self, page=1, limit=60, search='', movie_id=''):
        self.pagination(page, limit)
        with self.store.connect() as db:
            db.create_function('casefold', 1, str.casefold, deterministic=True)
            db.execute('BEGIN')
            source = ' FROM custom_lists l WHERE instr(casefold(l.name),?)>0'
            total = db.execute('SELECT count(*)' + source, (search.strip().casefold(),)).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            rows = db.execute('SELECT l.id,l.name,(SELECT count(*) FROM list_movies lm JOIN catalog c '
                              'ON c.movie_id=lm.movie_id WHERE lm.list_id=l.id AND EXISTS '
                              '(SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)) count,'
                              'EXISTS (SELECT 1 FROM list_movies lm WHERE lm.list_id=l.id AND lm.movie_id=?) included'
                              + source + ' ORDER BY l.added DESC,l.id LIMIT ? OFFSET ?',
                              (movie_id, search.strip().casefold(), limit, (page - 1) * limit)).fetchall()
        return dict(items=[{**dict(r), 'included': bool(r['included'])} for r in rows],
                    total=total, page=page, limit=limit)

    def get_list(self, identity):
        with self.store.connect() as db:
            row = db.execute('SELECT l.id,l.name,(SELECT count(*) FROM list_movies lm JOIN catalog c '
                             'ON c.movie_id=lm.movie_id WHERE lm.list_id=l.id AND EXISTS '
                             '(SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)) count '
                             'FROM custom_lists l WHERE l.id=?', (identity,)).fetchone()
        if not row:
            raise CollectionNotFound('清单不存在')
        return dict(row)

    def save_list(self, name, identity=None):
        name = self.name(name, 80)
        try:
            with self.store.connect() as db:
                if identity is None:
                    identity = secrets.token_hex(12)
                    db.execute('INSERT INTO custom_lists VALUES (?,?,?)', (identity, name, time.time()))
                elif not db.execute('UPDATE custom_lists SET name=? WHERE id=?', (name, identity)).rowcount:
                    raise CollectionNotFound('清单不存在')
        except sqlite3.IntegrityError as error:
            raise ValueError('已有同名清单，请使用其他名称') from error
        return self.get_list(identity)

    def delete_list(self, identity):
        with self.store.connect() as db:
            if not db.execute('DELETE FROM custom_lists WHERE id=?', (identity,)).rowcount:
                raise CollectionNotFound('清单不存在')
        return dict(deleted=True)

    def include_movie(self, identity, movie_id, included):
        if not isinstance(movie_id, str) or not movie_id or type(included) is not bool:
            raise ValueError('movie_id 须为影片 ID，included 须为布尔值')
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM custom_lists WHERE id=?', (identity,)).fetchone():
                raise CollectionNotFound('清单不存在')
            if included:
                if not db.execute('SELECT 1 FROM catalog c WHERE c.movie_id=? AND EXISTS '
                                  '(SELECT 1 FROM resources r WHERE r.movie_id=c.movie_id)', (movie_id,)).fetchone():
                    raise CollectionNotFound('影片不存在')
                db.execute('INSERT OR IGNORE INTO list_movies VALUES (?,?,?)', (identity, movie_id, time.time()))
            else:
                db.execute('DELETE FROM list_movies WHERE list_id=? AND movie_id=?', (identity, movie_id))
        return dict(included=included)
