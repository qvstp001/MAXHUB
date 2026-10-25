"""迅雷字幕库的片名检索与受限单文件读取。"""
from __future__ import annotations

import base64
import binascii
import json
import re
from urllib.parse import urlsplit

import httpx

from .catalog_rules import release_code_from_text
from .subtitle_search import MAX_BYTES, PAGE_SIZE, SubtitleSearchError, _client, _matches, convert

API = 'https://api-shoulei-ssl.xunlei.com/oracle/subtitle'
SITE = 'https://subtitle.v.geilijiasu.com'
PATH = re.compile(r'/[A-Fa-f0-9]{2}/[A-Fa-f0-9]{2}/[A-Fa-f0-9]{40}\.(srt|ass|ssa|vtt)')


def _url(value: str) -> str:
    try:
        url = urlsplit(value)
        valid = url.port in (None, 443)
    except ValueError as error:
        raise SubtitleSearchError('字幕下载地址不受支持') from error
    if not valid or url.scheme != 'https' or url.hostname != 'subtitle.v.geilijiasu.com' or url.username \
            or url.password or url.query or url.fragment or not PATH.fullmatch(url.path):
        raise SubtitleSearchError('字幕下载地址不受支持')
    return url.geturl()


def _get(client: httpx.Client, url: str, params=None) -> bytes:
    try:
        for _ in range(4):
            with client.stream('GET', url, params=params) as response:
                if response.is_redirect:
                    url = _url(str(response.url.join(response.headers.get('location', ''))))
                    params = None
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise SubtitleSearchError('字幕响应超过 4 MiB')
                return bytes(data)
    except httpx.HTTPError as error:
        raise SubtitleSearchError('迅雷字幕库暂时无法连接，请稍后重试') from error
    raise SubtitleSearchError('字幕下载重定向次数过多')


def _id(row: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(row, ensure_ascii=False).encode()).decode().rstrip('=')


def _detail(subtitle_id: str) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,1600}', subtitle_id):
        raise SubtitleSearchError('字幕编号无效')
    try:
        row = json.loads(base64.b64decode(subtitle_id + '=' * (-len(subtitle_id) % 4), altchars=b'-_', validate=True))
        if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in ('url', 'name', 'language')) \
                or not 1 <= len(row['name']) <= 200 or len(row['language']) > 80:
            raise ValueError
        row['url'] = _url(row['url'])
        return row
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise SubtitleSearchError('字幕编号无效') from error


def search(query: str, offset: int = 0) -> dict:
    query = query.strip()
    if not 3 <= len(query) <= 200 or not 0 <= offset < 60 or offset % PAGE_SIZE:
        raise SubtitleSearchError('搜索词需为 3–200 个字符，分页位置无效时请重新搜索')
    code = release_code_from_text(query)
    with _client() as client:
        try:
            payload = json.loads(_get(client, API, params={'name': code or query}))
        except (ValueError, UnicodeError) as error:
            raise SubtitleSearchError('迅雷字幕库搜索结果未取得，请稍后重试') from error
    if not isinstance(payload, dict) or payload.get('code') != 0 or not isinstance(payload.get('data'), list):
        raise SubtitleSearchError('迅雷字幕库搜索结果未取得，请稍后重试')
    candidates = {}
    for item in payload['data']:
        if not isinstance(item, dict):
            continue
        title = str(item.get('name') or '')[:200]
        if not title or (code and not _matches(title, code)):
            continue
        try:
            url = _url(str(item.get('url') or ''))
        except SubtitleSearchError:
            continue
        languages = item.get('languages')
        language = ' / '.join(str(value) for value in languages if value)[:80] if isinstance(languages, list) else ''
        row = {'url': url, 'name': title, 'language': language or '语言未标注'}
        candidates.setdefault(url, {'id': _id(row), 'title': title, 'language': row['language'],
                                    'format': url.rsplit('.', 1)[-1].upper()})
    rows = list(candidates.values())[:60]
    return {'results': rows[offset:offset + PAGE_SIZE], 'more': offset + PAGE_SIZE < len(rows), 'source': '迅雷字幕库'}


def files(subtitle_id: str) -> dict:
    row = _detail(subtitle_id)
    return {'files': [{'index': 0, 'name': row['name'], 'language': row['language'], 'playable': True}]}


def load(subtitle_id: str, index: int) -> str:
    row = _detail(subtitle_id)
    if index != 0:
        raise SubtitleSearchError('字幕文件不存在')
    with _client() as client:
        return convert(_get(client, row['url']), row['url'].rsplit('.', 1)[-1])
