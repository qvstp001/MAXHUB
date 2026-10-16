import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / 'qmaxhub.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS movies (
                    id TEXT PRIMARY KEY, metadata TEXT NOT NULL, added REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY, movie_id TEXT NOT NULL, root TEXT NOT NULL,
                    path TEXT NOT NULL, target TEXT NOT NULL, available INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, seen TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS resources_movie ON resources(movie_id);
                CREATE TABLE IF NOT EXISTS user_state (
                    movie_id TEXT PRIMARY KEY, favorite INTEGER DEFAULT 0,
                    watched INTEGER DEFAULT 0, rating INTEGER DEFAULT 0, last_played REAL);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL);
            ''')
            for key in ('api_key', 'signing_key', 'server_id'):
                db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (key, json.dumps(secrets.token_hex(24))))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else default

    def put(self, values):
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',
                           [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()])

    def movies(self):
        with self.connect() as db:
            movies = db.execute('SELECT m.*, s.favorite,s.watched,s.rating,s.last_played FROM movies m LEFT JOIN user_state s ON s.movie_id=m.id WHERE EXISTS (SELECT 1 FROM resources r WHERE r.movie_id=m.id)').fetchall()
            resources = db.execute('SELECT id,movie_id,root,path,available FROM resources ORDER BY path COLLATE NOCASE').fetchall()
        grouped = {}
        for row in resources:
            grouped.setdefault(row['movie_id'], []).append(dict(row))
        result = []
        for row in movies:
            item = json.loads(row['metadata'])
            item.update(id=row['id'], added=row['added'], favorite=bool(row['favorite']),
                        watched=bool(row['watched']), rating=row['rating'] or 0, last_played=row['last_played'])
            item['resources'] = grouped.get(row['id'], [])
            item['available'] = any(r['available'] for r in item['resources'])
            result.append(item)
        return result

    def movie(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT m.*,s.favorite,s.watched,s.rating,s.last_played FROM movies m LEFT JOIN user_state s ON s.movie_id=m.id WHERE m.id=?', (identity,)).fetchone()
            resources = db.execute('SELECT id,movie_id,root,path,available FROM resources WHERE movie_id=? ORDER BY path COLLATE NOCASE', (identity,)).fetchall()
        if not row:
            return None
        item = json.loads(row['metadata'])
        item.update(id=row['id'], added=row['added'], favorite=bool(row['favorite']),
                    watched=bool(row['watched']), rating=row['rating'] or 0, last_played=row['last_played'])
        item['resources'] = [dict(r) for r in resources]
        item['available'] = any(r['available'] for r in resources)
        return item

    def resource(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT * FROM resources WHERE id=?', (identity,)).fetchone()
        return dict(row) if row else None

    def state(self, identity, values):
        allowed = {'favorite', 'watched', 'rating', 'last_played'}
        if not values or set(values) - allowed:
            raise ValueError('无效的收藏状态')
        for key, value in values.items():
            if key in ('favorite', 'watched') and type(value) is not bool:
                raise ValueError('收藏和观看状态必须为布尔值')
            if key == 'rating' and (type(value) is not int or not 0 <= value <= 5):
                raise ValueError('个人评分范围为 0–5')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO user_state(movie_id) VALUES (?)', (identity,))
            for key, value in values.items():
                db.execute(f'UPDATE user_state SET {key}=? WHERE movie_id=?', (value, identity))
