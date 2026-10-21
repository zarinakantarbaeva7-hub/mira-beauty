import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
import app

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = app.DB_PATH
        app.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        self.valid = dict(name='Тестовый студент', phone='+7 (900) 123-45-67', service='laptop', visit_date=date.today().isoformat(), problem='Не включается ноутбук', consent=True)
    def tearDown(self):
        app.DB_PATH = self.old
        self.temp.cleanup()
    def request(self, path, method='GET', data=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        status = []
        result = app.application({'PATH_INFO':path, 'REQUEST_METHOD':method,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)}, lambda s,h:status.append(s))
        return int(status[0].split()[0]), b''.join(result)
    def test_catalog(self):
        status, body = self.request('/api/services')
        self.assertEqual(status,200)
        services=json.loads(body)
        self.assertEqual(len({s['image'] for s in services}),4)
        for service in services:
            self.assertEqual(self.request('/assets/'+service['image'])[0],200)
    def test_create_persists_and_private(self):
        status, body=self.request('/api/requests','POST',self.valid)
        self.assertEqual(status,201)
        rid=json.loads(body)['id']
        with app.connect() as conn:
            self.assertEqual(conn.execute('SELECT name FROM requests WHERE id=?',(rid,)).fetchone()[0],self.valid['name'])
        self.assertEqual(self.request('/api/requests')[0],404)
        self.assertEqual(self.request('/../app.py')[0],404)
        self.assertEqual(self.request('/data/requests.sqlite3')[0],404)
    def test_invalid_not_saved(self):
        bad=dict(self.valid, phone='abc',name=' ',service='unknown',problem='x',visit_date=(date.today()-timedelta(days=1)).isoformat(),consent=False)
        status,body=self.request('/api/requests','POST',bad)
        self.assertEqual(status,422)
        self.assertEqual(len(json.loads(body)['errors']),6)
        with app.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM requests').fetchone()[0],0)
    def test_bad_payloads(self):
        for raw in (b'{broken',b'\xff'):
            self.assertEqual(self.request('/api/requests','POST',raw=raw)[0],400)
        for payload in ([],None,{'name':2}):
            self.assertEqual(self.request('/api/requests','POST',raw=json.dumps(payload).encode())[0],422)
        self.assertEqual(self.request('/api/requests','POST',raw=b'x'*9000)[0],413)
    def test_sql_is_parameterized(self):
        data=dict(self.valid,name="Robert'); DROP TABLE requests;--")
        self.assertEqual(self.request('/api/requests','POST',data)[0],201)
        with app.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM requests').fetchone()[0],1)
    def test_pages(self):
        for path in ('/','/styles.css','/app.js','/privacy.html','/assets/hero.svg'):
            self.assertEqual(self.request(path)[0],200)

if __name__=='__main__':
    unittest.main()
