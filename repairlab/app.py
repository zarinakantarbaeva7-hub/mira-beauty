"""RepairLab: WSGI-сервер, JSON API и SQLite. Python 3.10+."""
import json
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from wsgiref.simple_server import make_server
from mimetypes import guess_type

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get('DB_PATH', ROOT / 'data' / 'requests.sqlite3'))
SERVICES = [
    {'id': 'laptop', 'title': 'Ноутбуки', 'description': 'Чистка, замена комплектующих и восстановление системы.', 'price': 3500, 'image': 'laptop.svg', 'category': 'Компьютеры'},
    {'id': 'phone', 'title': 'Смартфоны', 'description': 'Замена экрана, аккумулятора и разъёма зарядки.', 'price': 2500, 'image': 'phone.svg', 'category': 'Мобильные'},
    {'id': 'pc', 'title': 'Компьютеры', 'description': 'Сборка, диагностика и обновление вашего ПК.', 'price': 2000, 'image': 'pc.svg', 'category': 'Компьютеры'},
    {'id': 'tablet', 'title': 'Планшеты', 'description': 'Помощь с экраном, питанием и программными сбоями.', 'price': 3000, 'image': 'tablet.svg', 'category': 'Мобильные'},
]

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS requests
        (id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
         service TEXT NOT NULL, visit_date TEXT NOT NULL, problem TEXT NOT NULL,
         created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Новая')''')
    return conn


def validate(data):
    errors = {}
    if not isinstance(data, dict):
        return {'form': 'Ожидается JSON-объект.'}
    for key in ('name', 'phone', 'service', 'visit_date', 'problem'):
        if not isinstance(data.get(key), str):
            errors[key] = 'Заполните поле.'
    if errors:
        return errors
    if not 2 <= len(data['name'].strip()) <= 60:
        errors['name'] = 'Имя должно содержать от 2 до 60 символов.'
    if not re.fullmatch(r'\+?[\d\s()\-]{10,25}', data['phone']) or not 10 <= len(re.sub(r'\D', '', data['phone'])) <= 15:
        errors['phone'] = 'Укажите номер: от 10 до 15 цифр.'
    if data['service'] not in {s['id'] for s in SERVICES}:
        errors['service'] = 'Выберите услугу из списка.'
    try:
        chosen = date.fromisoformat(data['visit_date'])
        if not 0 <= (chosen - date.today()).days <= 90:
            raise ValueError
    except ValueError:
        errors['visit_date'] = 'Выберите дату от сегодня до 90 дней вперёд.'
    if not 10 <= len(data['problem'].strip()) <= 1000:
        errors['problem'] = 'Опишите проблему: от 10 до 1000 символов.'
    if data.get('consent') is not True:
        errors['consent'] = 'Для заявки необходимо согласие на обработку данных.'
    return errors


def application(environ, start_response):
    def respond(status, payload, content_type='application/json; charset=utf-8'):
        body = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, (dict, list)) else payload
        start_response(status, [('Content-Type', content_type), ('Content-Length', str(len(body))),
            ('X-Content-Type-Options', 'nosniff'), ('Cache-Control', 'no-store'),
            ('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")])
        return [body]
    path, method = environ.get('PATH_INFO', '/'), environ['REQUEST_METHOD']
    try:
        if path == '/api/health' and method == 'GET':
            with connect() as conn:
                conn.execute('SELECT 1')
            return respond('200 OK', {'ok': True})
        if path == '/api/services' and method == 'GET':
            return respond('200 OK', SERVICES)
        if path == '/api/requests' and method == 'POST':
            if environ.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                return respond('415 Unsupported Media Type', {'message': 'Требуется application/json.'})
            try:
                length = int(environ.get('CONTENT_LENGTH') or 0)
                if length > 8192:
                    return respond('413 Payload Too Large', {'message': 'Слишком большой запрос.'})
                data = json.loads(environ['wsgi.input'].read(length))
            except (ValueError, UnicodeDecodeError):
                return respond('400 Bad Request', {'message': 'Некорректный JSON.'})
            errors = validate(data)
            if errors:
                return respond('422 Unprocessable Entity', {'message': 'Проверьте поля формы.', 'errors': errors})
            request_id = secrets.token_hex(5).upper()
            with connect() as conn:
                conn.execute('INSERT INTO requests (id,name,phone,service,visit_date,problem,created_at) VALUES (?,?,?,?,?,?,?)',
                    (request_id, data['name'].strip(), data['phone'].strip(), data['service'], data['visit_date'], data['problem'].strip(), datetime.now(timezone.utc).isoformat()))
            return respond('201 Created', {'id': request_id, 'message': 'Заявка принята! Сохраните её номер. Мы свяжемся с вами для подтверждения.'})
        if path.startswith('/api/'):
            return respond('404 Not Found', {'message': 'Маршрут не найден.'})
        if method not in ('GET', 'HEAD'):
            return respond('405 Method Not Allowed', {'message': 'Метод не поддерживается.'})
        relative = 'index.html' if path == '/' else path.removeprefix('/')
        file = (ROOT / 'static' / relative).resolve()
        if not file.is_relative_to((ROOT / 'static').resolve()) or not file.is_file():
            return respond('404 Not Found', b'Page not found', 'text/plain; charset=utf-8')
        body = file.read_bytes()
        if method == 'HEAD':
            body = b''
        mime = guess_type(file.name)[0] or 'application/octet-stream'
        return respond('200 OK', body, mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
    except (sqlite3.Error, OSError):
        return respond('503 Service Unavailable', {'message': 'Не удалось сохранить данные. Попробуйте позже.'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    print(f'RepairLab: http://localhost:{port}')
    with make_server('0.0.0.0', port, application) as server:
        server.serve_forever()
