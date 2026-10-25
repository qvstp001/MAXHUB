"""迅雷字幕库的协议、分页、文本转换与下载边界。"""
import unittest
from unittest import mock

import httpx

from peach import subtitle_xunlei as source
from peach.subtitle_search import MAX_BYTES, SubtitleSearchError

URL = source.SITE + '/AA/BB/' + 'A' * 40 + '.srt'
SRT = '1\n00:00:00,000 --> 00:00:02,000\n测试字幕\n'


def row(name='ABP-758.srt', url=URL, languages=None):
    return dict(name=name, url=url, ext='srt', languages=['简体'] if languages is None else languages)


class XunleiSubtitleTests(unittest.TestCase):
    def client(self, handler):
        return mock.patch.object(source, '_client', return_value=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_search_normalizes_code_filters_identities_and_deduplicates(self):
        def respond(request):
            self.assertEqual(str(request.url).split('?')[0], source.API)
            self.assertEqual(request.url.params['name'], 'ABP-758')
            return httpx.Response(200, json={'code': 0, 'data': [row(), row(), row('ABP-7580.srt'),
                row('XABP-758.srt'), row(url='https://evil.example/test.srt'), {'name': 'ABP-758'}]})
        with self.client(respond):
            payload = source.search('abp00758')
        self.assertEqual(payload['source'], '迅雷字幕库')
        self.assertEqual(len(payload['results']), 1)
        self.assertFalse(payload['more'])
        self.assertEqual(payload['results'][0]['language'], '简体')
        self.assertEqual(source.files(payload['results'][0]['id'])['files'], [
            {'index': 0, 'name': 'ABP-758.srt', 'language': '简体', 'playable': True}])

    def test_keyword_search_and_pagination_keep_languages_and_supported_formats(self):
        rows = [row(f'电影 {index}.srt', source.SITE + f'/AA/BB/{index:040X}.srt', ['英语']) for index in range(7)]
        def respond(request):
            self.assertEqual(request.url.params['name'], '电影片名')
            return httpx.Response(200, json={'code': 0, 'data': rows})
        with self.client(respond):
            first = source.search('电影片名')
        with self.client(respond):
            second = source.search('电影片名', 6)
        self.assertEqual(len(first['results']), 6)
        self.assertTrue(first['more'])
        self.assertEqual(second['results'][0]['title'], '电影 6.srt')
        self.assertFalse(second['more'])
        self.assertEqual(first['results'][0]['language'], '英语')

    def test_loading_uses_text_converter_and_has_no_disk_side_effect(self):
        subtitle_id = source._id(dict(url=URL, name='测试.srt', language='简体'))
        with self.client(lambda request: httpx.Response(200, content=SRT.encode('gbk'))):
            text = source.load(subtitle_id, 0)
        self.assertIn('测试字幕', text)
        self.assertIn('00:00:00.000 --> 00:00:02.000', text)
        with self.assertRaisesRegex(SubtitleSearchError, '不存在'):
            source.load(subtitle_id, 1)

    def test_untrusted_urls_ids_redirects_and_oversized_payloads_are_refused(self):
        for url in ('http://subtitle.v.geilijiasu.com/AA/BB/' + 'A' * 40 + '.srt',
                    URL + '?target=private', URL + '#fragment', URL.replace('.com/', '.com.evil.example/'),
                    'https://127.0.0.1/test.srt', source.SITE + '/AA/BB/%2e%2e/test.srt',
                    URL.replace('.srt', '.zip'), URL.replace('.com/', '.com:invalid/')):
            with self.subTest(url=url), self.assertRaises(SubtitleSearchError):
                source._url(url)
        for value in ('invalid!', 'bm90LWpzb24', source._id({'url': URL, 'name': [], 'language': ''})):
            with self.subTest(value=value), self.assertRaises(SubtitleSearchError):
                source.files(value)
        subtitle_id = source._id(dict(url=URL, name='测试.srt', language='简体'))
        for response in (httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'}),
                         httpx.Response(200, content=b'x' * (MAX_BYTES + 1))):
            with self.client(lambda request, response=response: response), self.assertRaises(SubtitleSearchError):
                source.load(subtitle_id, 0)

    def test_api_errors_and_query_limits_are_actionable(self):
        for response in (httpx.Response(503), httpx.Response(200, text='captcha'),
                         httpx.Response(200, json={'code': 1, 'data': []}),
                         httpx.Response(200, json={'code': 0, 'data': None})):
            with self.client(lambda request, response=response: response), self.assertRaises(SubtitleSearchError):
                source.search('ABP-758')
        for query, offset in (('ab', 0), ('ABP-758', -1), ('ABP-758', 1), ('ABP-758', 60)):
            with self.assertRaises(SubtitleSearchError):
                source.search(query, offset)
