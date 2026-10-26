"""列表快速路径的版次语义与人物页面结构缓存失效边界。"""
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from peach import catalog_rules, web_entity
from peach.performer_profiles import write_profile
from peach.web_contract import WebContract
from support.ledger import fresh_ledger


class EditionSuffixTests(unittest.TestCase):
    def test_plain_codes_glued_markers_and_tag_evidence(self):
        for index in range(1, 101):
            code = f'SSIS-{index:03d}'
            for suffix, expected in (('', []), ('C', ['中字']), ('CH', ['中字']), ('SUB', ['中字']),
                                     ('U', ['无码']), ('UC', ['无码']), ('-UN', ['无码']),
                                     ('-uncensored', ['无码']), ('-中文字幕', ['中字']),
                                     ('-无码破解', ['无码破解']), ('CHAPTER', []), ('-UHD', [])):
                with self.subTest(code=code, suffix=suffix):
                    self.assertEqual(catalog_rules.jav_edition_badges(code + suffix + '.strm', code), expected)
            self.assertEqual(catalog_rules.jav_edition_badges(code + '.strm', code, ['中字', '无码']), ['中字', '无码'])
        self.assertEqual(catalog_rules.jav_edition_badges('n0646.mp4', 'n646'), ['无码'])
        self.assertEqual(catalog_rules.jav_edition_badges('FC2-PPV-001234567C.strm', 'FC2-PPV-1234567'), ['中字'])


class EntityShapesCacheTests(unittest.TestCase):
    def test_repeated_reads_reuse_shape_and_external_writes_refresh_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = fresh_ledger(Path(directory))
            contract = WebContract(path)
            try:
                with mock.patch.object(web_entity, '_read_entity_shapes', wraps=web_entity._read_entity_shapes) as read:
                    first = web_entity.q_entity_shapes(contract, {})
                    self.assertEqual(first, web_entity.q_entity_shapes(contract, {}))
                    self.assertEqual(read.call_count, 1)
                    with contextlib.closing(sqlite3.connect(path)) as db, db:
                        db.execute("INSERT INTO entity(id,kind,canonical_name,normalized_name,created_at,updated_at) "
                                   "VALUES(1,'performer','示例','示例','test','test')")
                        db.execute("INSERT INTO entity_alias(entity_id,alias,normalized_alias,source) "
                                   "VALUES(1,'示例别名','示例别名','test')")
                        write_profile(db, 1, {'height_cm': 160}, source='auto:test', source_url='')
                    refreshed = web_entity.q_entity_shapes(contract, {})
                    self.assertEqual(read.call_count, 2)
                    self.assertEqual(refreshed['entities'][0]['names'], ['示例', '示例别名'])
                    self.assertIn('facts', refreshed['entities'][0]['parts'])
                    self.assertEqual(web_entity.q_entity_shapes(contract, {}), refreshed)
                    self.assertEqual(read.call_count, 2)
            finally:
                contract.stop_background_jobs()
