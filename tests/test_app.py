"""Проверки настоящих HTTP-сценариев без изменения рабочей базы салона."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ElementTree
from zoneinfo import ZoneInfo

from werkzeug.security import check_password_hash, generate_password_hash
from app import create_admin, create_app
from data import GALLERY


class MiraBeautyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'test.sqlite3'
        self.app = create_app({
            'TESTING': True,
            'DATABASE': str(self.database),
            'SECRET_KEY': 'only-for-automated-tests',
        })
        self.client = self.app.test_client()
        self.tomorrow = (datetime.now(ZoneInfo('Asia/Qyzylorda')).date()
                         + timedelta(days=1)).isoformat()
        self.payload = {
            'name': 'Тестовый клиент', 'phone': '+7 (700) 123-45-67',
            'service': 'hair', 'master': 'amina',
            'visit_date': self.tomorrow, 'visit_time': '10:00',
            'comment': 'Демонстрационная заявка', 'consent': True,
        }

    def tearDown(self):
        self.directory.cleanup()

    def csrf(self, client=None):
        client = client or self.client
        response = client.get('/api/csrf')
        self.assertEqual(response.status_code, 200)
        return response.get_json()['csrf_token']

    def post_booking(self, changes=None, client=None):
        client = client or self.client
        payload = dict(self.payload)
        payload.update(changes or {})
        return client.post('/api/bookings', json=payload,
                           headers={'X-CSRFToken': self.csrf(client)})

    def sql(self, query, params=()):
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(query, params)]

    def add_admin(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                'INSERT INTO admins (username, password_hash) VALUES (?, ?)',
                ('testadmin', generate_password_hash('TestPassword123!')))

    def login(self):
        self.add_admin()
        response = self.client.post('/login', data={
            'username': 'testadmin', 'password': 'TestPassword123!',
            'csrf_token': self.csrf(),
        })
        self.assertIn(response.status_code, (302, 303))
        self.assertIn('/admin', response.headers['Location'])

    def test_public_pages_and_unknown_route(self):
        for path in ('/', '/services', '/masters', '/gallery', '/booking',
                     '/about', '/privacy', '/login'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/no-such-page').status_code, 404)
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_catalog_and_master_compatibility(self):
        response = self.client.get('/api/services')
        self.assertEqual(response.status_code, 200)
        services = response.get_json()
        self.assertEqual(len(services), 6)
        self.assertEqual(len({s['id'] for s in services}), 6)
        self.assertEqual(len({s['image'] for s in services}), 6)
        masters = self.client.get('/api/masters?service=hair').get_json()
        self.assertEqual([m['id'] for m in masters], ['amina'])

    def test_success_is_persisted_in_sqlite(self):
        response = self.post_booking({'name': '  Тестовый клиент  '})
        self.assertEqual(response.status_code, 201, response.get_json())
        result = response.get_json()
        self.assertTrue(result['id'])
        saved = self.sql('SELECT * FROM bookings WHERE id=?', (result['id'],))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['name'], 'Тестовый клиент')
        self.assertEqual(saved[0]['master'], 'amina')
        self.assertEqual(saved[0]['visit_time'], '10:00')
        self.assertEqual(saved[0]['status'], 'new')

    def test_invalid_fields_do_not_create_rows(self):
        cases = [
            {'name': ' '}, {'name': 'x' * 61}, {'phone': 'abc'},
            {'phone': '1' * 16}, {'service': 'unknown'},
            {'master': 'unknown'}, {'master': 'dana'},
            {'visit_date': '2000-01-01'}, {'visit_date': 'not-a-date'},
            {'visit_time': '03:00'}, {'visit_time': '10:12'},
            {'comment': 'x' * 501}, {'consent': False}, {'consent': 'true'},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.post_booking(changes)
                self.assertEqual(response.status_code, 422, response.get_json())
        self.assertEqual(self.sql('SELECT count(*) AS n FROM bookings')[0]['n'], 0)

    def test_csrf_is_required_for_booking(self):
        response = self.client.post('/api/bookings', json=self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM bookings')[0]['n'], 0)

    def test_unicode_csrf_is_rejected_without_a_server_error(self):
        self.csrf()
        response = self.client.post('/api/bookings', json=self.payload,
                                    headers={'X-CSRFToken': 'тест'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM bookings')[0]['n'], 0)

    def test_malformed_and_oversized_payloads(self):
        token = self.csrf()
        for raw in ('{broken', 'null', '[]', '"text"'):
            with self.subTest(raw=raw):
                response = self.client.post(
                    '/api/bookings', data=raw, content_type='application/json',
                    headers={'X-CSRFToken': token})
                self.assertEqual(response.status_code, 400)
        response = self.client.post(
            '/api/bookings', data='x' * 20000,
            content_type='application/json', headers={'X-CSRFToken': token})
        self.assertEqual(response.status_code, 413)

    def test_sql_parameters_preserve_customer_text(self):
        name = "Robert'); DROP TABLE bookings;--"
        response = self.post_booking({'name': name})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.sql('SELECT name FROM bookings')[0]['name'], name)

    def test_availability_excludes_overlaps(self):
        response = self.client.get('/api/availability', query_string={
            'service': 'hair', 'master': 'amina', 'date': self.tomorrow})
        self.assertEqual(response.status_code, 200)
        self.assertIn('10:00', response.get_json()['slots'])
        self.assertEqual(self.post_booking().status_code, 201)
        response = self.client.get('/api/availability', query_string={
            'service': 'hair', 'master': 'amina', 'date': self.tomorrow})
        slots = response.get_json()['slots']
        self.assertNotIn('10:00', slots)
        self.assertNotIn('10:30', slots)
        self.assertIn('11:00', slots)

    def test_overlap_is_rejected_but_adjacent_and_other_master_allowed(self):
        self.assertEqual(self.post_booking().status_code, 201)
        self.assertEqual(self.post_booking({'visit_time': '10:30'}).status_code, 409)
        self.assertEqual(self.post_booking({'visit_time': '11:00'}).status_code, 201)
        self.assertEqual(self.post_booking({
            'service': 'nails', 'master': 'dana'}).status_code, 201)

    def test_long_service_blocks_its_whole_duration(self):
        self.assertEqual(self.post_booking({'service': 'color'}).status_code, 201)
        self.assertEqual(self.post_booking({'visit_time': '12:00'}).status_code, 409)
        self.assertEqual(self.post_booking({'visit_time': '13:00'}).status_code, 201)
        response = self.post_booking({'service': 'color', 'visit_time': '18:00'})
        self.assertIn(response.status_code, (409, 422))

    def test_invalid_availability_parameters(self):
        cases = [
            {'service': 'bad', 'master': 'amina', 'date': self.tomorrow},
            {'service': 'hair', 'master': 'dana', 'date': self.tomorrow},
            {'service': 'hair', 'master': 'amina', 'date': '2000-01-01'},
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(self.client.get(
                    '/api/availability', query_string=query).status_code, 422)

    def test_simultaneous_requests_cannot_double_book(self):
        clients = [self.app.test_client(), self.app.test_client()]
        tokens = [self.csrf(c) for c in clients]
        barrier = threading.Barrier(2)
        def submit(index):
            barrier.wait(timeout=10)
            return clients[index].post(
                '/api/bookings', json=self.payload,
                headers={'X-CSRFToken': tokens[index]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, (0, 1)))
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM bookings')[0]['n'], 1)

    def test_private_admin_and_database_are_not_public(self):
        for path in ('/admin', '/admin/export.csv'):
            response = self.client.get(path)
            self.assertIn(response.status_code, (302, 303))
            self.assertIn('/login', response.headers['Location'])
        for path in ('/instance/beauty.sqlite3', '/app.py', '/data.py'):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertIn(self.client.get('/api/bookings').status_code, (404, 405))

    def test_wrong_password_does_not_authenticate(self):
        self.add_admin()
        response = self.client.post('/login', data={
            'username': 'testadmin', 'password': 'wrong-password',
            'csrf_token': self.csrf()})
        self.assertIn(response.status_code, (200, 401))
        self.assertIn(self.client.get('/admin').status_code, (302, 303))
        self.assertNotEqual(self.sql('SELECT password_hash FROM admins')[0]['password_hash'],
                            'TestPassword123!')

    def test_admin_can_cancel_and_release_slot(self):
        created = self.post_booking().get_json()
        self.login()
        self.assertEqual(self.client.get('/admin').status_code, 200)
        url = f"/admin/bookings/{created['id']}/status"
        self.assertEqual(self.client.post(url, data={'status': 'cancelled'}).status_code, 403)
        response = self.client.post(url, data={
            'status': 'cancelled', 'csrf_token': self.csrf()})
        self.assertIn(response.status_code, (302, 303))
        self.assertEqual(self.sql('SELECT status FROM bookings')[0]['status'], 'cancelled')
        self.assertEqual(self.post_booking().status_code, 201)

    def test_cancelled_booking_cannot_be_restored_over_another_booking(self):
        first = self.post_booking().get_json()['id']
        self.login()
        url = f'/admin/bookings/{first}/status'
        response = self.client.post(url, data={
            'status': 'cancelled', 'csrf_token': self.csrf()})
        self.assertIn(response.status_code, (302, 303))
        self.assertEqual(self.post_booking().status_code, 201)
        response = self.client.post(url, data={
            'status': 'confirmed', 'csrf_token': self.csrf()})
        self.assertIn(response.status_code, (302, 303, 409))
        self.assertEqual(self.sql('SELECT status FROM bookings WHERE id=?',
                                  (first,))[0]['status'], 'cancelled')

    def test_customer_text_is_escaped_in_admin_html(self):
        self.assertEqual(self.post_booking({
            'name': '<script>alert(1)</script>'}).status_code, 201)
        self.login()
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', text)
        self.assertNotIn('<script>alert(1)</script>', text)

    def test_admin_csv_neutralizes_formulas(self):
        self.assertEqual(self.post_booking({'name': '=1+1'}).status_code, 201)
        self.login()
        response = self.client.get('/admin/export.csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))
        text = response.data.decode('utf-8-sig')
        self.assertIn("'=1+1", text)
        self.assertIn("'+7", text)

    def test_logout_removes_access(self):
        self.login()
        response = self.client.post('/logout', data={'csrf_token': self.csrf()})
        self.assertIn(response.status_code, (302, 303))
        self.assertIn(self.client.get('/admin').status_code, (302, 303))

    def test_create_admin_requires_a_password_and_stores_only_its_hash(self):
        self.assertEqual(self.sql('SELECT count(*) AS n FROM admins')[0]['n'], 0)
        with self.assertRaises(ValueError):
            create_admin('operator', 'short', self.database)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM admins')[0]['n'], 0)
        create_admin('operator', 'DistinctPassword123!', self.database)
        row = self.sql('SELECT username,password_hash FROM admins')[0]
        self.assertEqual(row['username'], 'operator')
        self.assertNotEqual(row['password_hash'], 'DistinctPassword123!')
        self.assertTrue(check_password_hash(row['password_hash'], 'DistinctPassword123!'))
        with self.assertRaises(sqlite3.IntegrityError):
            create_admin('operator', 'AnotherPassword123!', self.database)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM admins')[0]['n'], 1)

    def test_all_illustrations_are_local_available_and_distinct(self):
        services = self.client.get('/api/services').get_json()
        masters = self.client.get('/api/masters').get_json()
        names = [row['image'] for row in services + masters + GALLERY]
        self.assertEqual(len(names), len(set(names)))
        image_hashes = []
        for name in names + ['hero.svg']:
            with self.subTest(image=name):
                self.assertNotIn('://', name)
                with self.client.get('/static/images/' + name) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/svg+xml')
                    tree = ElementTree.fromstring(response.data)
                    self.assertTrue(tree.tag.endswith('svg'))
                    image_hashes.append(hashlib.sha256(response.data).hexdigest())
        self.assertEqual(len(image_hashes), len(set(image_hashes)))

    def test_old_uploaded_database_is_migrated_without_data_loss(self):
        legacy = Path(self.directory.name) / 'legacy.sqlite3'
        with sqlite3.connect(legacy) as connection:
            connection.execute('CREATE TABLE bookings (id TEXT PRIMARY KEY, '
                               'name TEXT, phone TEXT, service TEXT, '
                               'visit_date TEXT, created_at TEXT)')
            connection.execute('INSERT INTO bookings VALUES (?,?,?,?,?,?)',
                               ('LEGACY123', 'Старая заявка', '+77001234567',
                                'hair', self.tomorrow, '2026-01-01T00:00:00+00:00'))
        migrated = create_app({'TESTING': True, 'DATABASE': str(legacy),
                               'SECRET_KEY': 'legacy-test'})
        with sqlite3.connect(legacy) as connection:
            connection.row_factory = sqlite3.Row
            row = dict(connection.execute('SELECT * FROM bookings').fetchone())
        self.assertEqual(row['id'], 'LEGACY123')
        self.assertEqual(row['name'], 'Старая заявка')
        self.assertIn('master', row)
        self.assertIn('visit_time', row)
        self.assertIn('status', row)
        self.assertEqual(migrated.test_client().get('/api/health').status_code, 200)


if __name__ == '__main__':
    unittest.main()
