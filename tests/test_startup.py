import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from qmaxhub import DEFAULT_ADMIN_PASSWORD

UNSET = object()
ROOT = Path(__file__).resolve().parent.parent


class StartupTest(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-data').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.test-data')
        self.directory = Path(self.temp.name)
        self.log = (self.directory / 'startup.log').open('wb')
        self.process = None

    def tearDown(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log.close()
        if not self.directory.resolve().is_relative_to(ROOT / '.test-data'):
            raise RuntimeError('Test cleanup target escaped workspace')
        self.temp.cleanup()

    def start(self, password=UNSET, wait=True):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': str(self.port),
               'PUBLIC_URL': f'http://127.0.0.1:{self.port}',
               'DATA_DIR': str(self.directory / 'data'), 'LIBRARY_ROOTS': '[]',
               'PLAYBACK_PROXY_URL': '', 'SCAN_INTERVAL': '0', 'COOKIE_SECURE': 'false',
               'PYTHONUTF8': '1'}
        env.pop('ADMIN_PASSWORD', None)
        if password is not UNSET:
            env['ADMIN_PASSWORD'] = password
        self.process = subprocess.Popen([sys.executable, '-m', 'qmaxhub'], cwd=ROOT,
                                        env=env, stdout=self.log, stderr=self.log)
        if not wait:
            return
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                if self.request('/health')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        self.fail('Service did not start: ' + (self.directory / 'startup.log').read_text(encoding='utf-8'))

    def request(self, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=2)
        try:
            conn.request('POST' if body is not None else 'GET', path,
                         json.dumps(body).encode() if body is not None else None,
                         {'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_missing_password_uses_initial_default(self):
        self.start()
        self.assertEqual(self.request('/api/movies')[0], 401)
        self.assertEqual(self.request('/api/login', {'password': DEFAULT_ADMIN_PASSWORD})[0], 200)

    def test_empty_password_uses_initial_default(self):
        self.start('')
        self.assertEqual(self.request('/api/login', {'password': ''})[0], 401)
        self.assertEqual(self.request('/api/login', {'password': DEFAULT_ADMIN_PASSWORD})[0], 200)

    def test_custom_password_overrides_initial_default(self):
        password = 'custom-startup-password'
        self.start(password)
        self.assertEqual(self.request('/api/login', {'password': DEFAULT_ADMIN_PASSWORD})[0], 401)
        self.assertEqual(self.request('/api/login', {'password': password})[0], 200)

    def test_invalid_custom_password_is_rejected(self):
        self.start('short', wait=False)
        self.assertNotEqual(self.process.wait(timeout=15), 0)
        self.assertIn('ADMIN_PASSWORD', (self.directory / 'startup.log').read_text(encoding='utf-8'))
