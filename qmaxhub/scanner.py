import hashlib
import json
import os
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}
VIDEO_EXT = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
             '.ts', '.m2ts', '.mts', '.mpg', '.mpeg', '.vob', '.3gp', '.ogv'}
MEDIA_EXT = VIDEO_EXT | {'.strm'}


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def bounded(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('路径超出媒体目录')
    return path


def read_limited(path, limit):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'文件过大：{Path(path).name}')
    return data.decode('utf-8-sig')


def strm_target(path):
    lines = [line.strip() for line in read_limited(path, 65536).splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1:
        raise ValueError('STRM 必须包含一个 HTTP(S) 播放地址')
    value = lines[0]
    url = urlsplit(value)
    if url.scheme not in ('http', 'https') or not url.hostname or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('仅支持 HTTP(S) STRM；不支持本地路径或 Kodi |Header 语法')
    if '|' in value:
        raise ValueError('暂不支持 Kodi |Header 语法')
    # Location headers must remain ASCII. Preserve all existing URL escaping/signatures.
    from urllib.parse import quote
    return quote(value, safe=":/?#[]@!$&'()*+,;=%-._~")


def nfo_metadata(path, root, stem, files):
    document = ET.Element('movie')
    if path:
        xml = read_limited(bounded(path, root), 2 * 1024 * 1024)
        if re.search(r'<!\s*(DOCTYPE|ENTITY)', xml, re.I):
            raise ValueError('NFO 不允许 DTD 或实体声明')
        document = ET.fromstring(xml)
        if document.tag != 'movie':
            raise ValueError('NFO 根节点必须为 movie')
    def text(name):
        return (document.findtext(name) or '').strip()
    code = text('num') or next(((n.text or '').strip() for n in document.findall('uniqueid') if n.get('type', '').lower() in ('num', 'jav', 'javid')), '') or text('id')
    if not code:
        match = re.search(r'(?i)([a-z]{2,12}[-_]\d{2,8}|\d{6}[-_]\d{2,4})', stem)
        code = match.group(1).replace('_', '-').upper() if match else ''
    def image(reference):
        if not reference or urlsplit(reference).scheme or reference.startswith('//'):
            return None
        base = path.parent if path else files[0].parent
        candidate = bounded(base / unquote(reference.replace('\\', '/')), root)
        return str(candidate) if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXT else None
    lookup = {p.name.casefold(): p for p in files}
    def local(names):
        for name in names:
            for ext in ('.jpg', '.jpeg', '.png', '.webp', '.avif'):
                candidate = lookup.get((name + ext).casefold())
                if candidate:
                    return str(bounded(candidate, root))
        return None
    poster = next((image(n.text) for n in document.findall('thumb') if n.get('aspect') == 'poster' and n.text), None)
    poster = poster or image(text('art/poster')) or local([stem + '-poster', stem + '.poster', 'poster', 'folder', stem + '-thumb', 'thumb', stem])
    cover = local([stem + '-landscape', stem + '-fanart', stem + '.fanart', 'fanart', stem + '-thumb', 'thumb', stem + '-cover', 'cover'])
    cover = cover or next((image(n.text) for n in document.findall('fanart/thumb') if n.text), None)
    poster = poster or next((image(n.text) for n in document.findall('thumb') if n.text), None) or cover
    actors = []
    for actor in document.findall('actor'):
        name = (actor.findtext('name') or '').strip()
        if name:
            thumb = image((actor.findtext('thumb') or '').strip())
            if not thumb:
                thumb = image('.actors/' + name.replace(' ', '_') + '.jpg')
            actors.append({'name': name, 'role': (actor.findtext('role') or '').strip(), 'thumb': thumb})
    samples = []
    for node in document.findall('fanart/thumb')[1:] + document.findall('sample'):
        value = image(node.text)
        if value and value != cover:
            samples.append(value)
    base = path.parent if path else files[0].parent
    for folder in ('extrafanart', 'screenshots', 'javdex-samples'):
        directory = bounded(base / folder, root)
        if directory.is_dir():
            candidates = sorted(directory.iterdir(), key=lambda p: [int(v) if v.isdigit() else v for v in re.split(r'(\d+)', p.name.casefold())])
            for candidate in candidates:
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXT and (folder != 'javdex-samples' or candidate.name.startswith(stem + '-')):
                    samples.append(str(bounded(candidate, root)))
    def number(value):
        try:
            n = float(value)
            return n if 0 <= n <= 100000 else 0
        except (ValueError, TypeError):
            return 0
    return dict(code=code.upper(), title=text('title') or stem, original_title=text('originaltitle'),
                plot=text('plot') or text('outline'), date=text('premiered') or text('releasedate') or text('release'),
                year=text('year'), studio=text('studio') or text('maker'), director=text('director'),
                series=text('set/name') or text('set'), runtime=number(text('runtime')),
                score=number(text('rating') or text('ratings/rating/value')),
                tags=list(dict.fromkeys((n.text or '').strip() for n in document.findall('tag') + document.findall('genre') if (n.text or '').strip())),
                actors=actors, poster=poster, cover=cover or poster, samples=list(dict.fromkeys(samples)),
                nfo=str(path) if path else None)


class Scanner:
    def __init__(self, store, roots):
        self.store, self.roots = store, [Path(r).resolve() for r in roots]
        self.lock = threading.Lock()
        self.status = {'running': False, 'processed': 0, 'errors': [], 'finished': None}

    def start(self):
        if not self.lock.acquire(blocking=False):
            return False
        self.status = {'running': True, 'processed': 0, 'errors': [], 'finished': None}
        threading.Thread(target=self.run, daemon=True).start()
        return True

    def run(self):
        generation = uuid.uuid4().hex
        try:
            for root in self.roots:
                try:
                    if not root.is_dir():
                        raise ValueError(f'目录不可用：{root}')
                    walk_errors = []
                    for folder, directories, filenames in os.walk(root, followlinks=False, onerror=walk_errors.append):
                        directories[:] = [d for d in directories if not d.startswith('.')]
                        files = [Path(folder) / f for f in filenames]
                        lookup = {p.name.casefold(): p for p in files}
                        streams = [p for p in files if p.suffix.lower() in MEDIA_EXT]
                        for stream in streams:
                            resource_id = identity(str(root) + '/' + stream.relative_to(root).as_posix())
                            try:
                                bounded(stream, root)
                                nfo = lookup.get((stream.stem + '.nfo').casefold())
                                part_stem = re.sub(r'(?i)[-_. ](?:cd|part|disc)\d+$', '', stream.stem)
                                nfo = nfo or lookup.get((part_stem + '.nfo').casefold())
                                # movie.nfo is unambiguous only in a single-title directory.
                                if not nfo and (len(streams) == 1 or all(re.sub(r'(?i)[-_. ](?:cd|part|disc)\d+$', '', s.stem) == re.sub(r'(?i)[-_. ](?:cd|part|disc)\d+$', '', stream.stem) for s in streams)):
                                    nfo = lookup.get('movie.nfo')
                                if not nfo and len(streams) == 1:
                                    candidates = [p for p in files if p.suffix.lower() == '.nfo']
                                    nfo = candidates[0] if len(candidates) == 1 else None
                                metadata = nfo_metadata(nfo, root, stream.stem, files)
                                # Native videos are opened only when played; never load them during scanning.
                                target = strm_target(stream) if stream.suffix.lower() == '.strm' else ''
                                movie_id = identity('code:' + metadata['code'] if metadata['code'] else 'path:' + resource_id)
                                with self.store.connect() as db:
                                    db.execute('INSERT INTO movies VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata',
                                               (movie_id, json.dumps(metadata, ensure_ascii=False), time.time()))
                                    db.execute('INSERT OR REPLACE INTO resources VALUES (?,?,?,?,?,?,?,?)',
                                               (resource_id, movie_id, str(root), str(stream), target, 1, '', generation))
                            except (OSError, ValueError, ET.ParseError) as error:
                                with self.store.connect() as db:
                                    db.execute('UPDATE resources SET available=0,seen=? WHERE id=?', (generation, resource_id))
                                self.error(stream, error)
                            self.status['processed'] += 1
                    if walk_errors:
                        for error in walk_errors:
                            self.error(root, error)
                    else:
                        with self.store.connect() as db:
                            db.execute('UPDATE resources SET available=0 WHERE root=? AND seen<>?', (str(root), generation))
                except (OSError, ValueError) as error:
                    self.error(root, error)
        except Exception as error:
            self.error('扫描任务', error)
        finally:
            finished = {**self.status, 'running': False, 'finished': time.time()}
            try:
                self.store.put({'last_scan': finished})
            finally:
                self.status = finished
                self.lock.release()

    def error(self, path, error):
        if len(self.status['errors']) < 200:
            self.status['errors'].append({'path': str(path), 'message': str(error)})
