"""Mira Beauty: Flask, SQLite, запись на свободное время и админка.

Запуск: python app.py. Создание администратора: python app.py setup-admin.
"""
import csv
import getpass
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from data import GALLERY, MASTERS, SERVICES, STATUS_LABELS

SALON_TZ = ZoneInfo('Asia/Qyzylorda')
SERVICE_MAP = {item['id']: item for item in SERVICES}
MASTER_MAP = {item['id']: item for item in MASTERS}


def salon_now():
    return datetime.now(SALON_TZ)


@contextmanager
def database(path):
    connection = sqlite3.connect(str(path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        yield connection
    finally:
        connection.close()


def init_database(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with database(path) as connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
            service TEXT NOT NULL, visit_date TEXT NOT NULL, created_at TEXT NOT NULL,
            master TEXT NOT NULL DEFAULT '', visit_time TEXT NOT NULL DEFAULT '',
            comment TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'new'
        )''')
        # Миграция присланной базы: старые заявки сохраняются.
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(bookings)')}
        additions = {'master': "TEXT NOT NULL DEFAULT ''", 'visit_time': "TEXT NOT NULL DEFAULT ''",
                     'comment': "TEXT NOT NULL DEFAULT ''", 'status': "TEXT NOT NULL DEFAULT 'new'"}
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(f'ALTER TABLE bookings ADD COLUMN {column} {definition}')
        connection.execute('CREATE INDEX IF NOT EXISTS booking_calendar ON bookings(master, visit_date, status)')
        connection.execute('''CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
        )''')
        connection.execute('''CREATE TABLE IF NOT EXISTS rate_limits (
            key TEXT PRIMARY KEY, hits INTEGER NOT NULL, reset_at REAL NOT NULL
        )''')
        connection.commit()


def create_admin(username, password, database_path):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,40}', username):
        raise ValueError('Логин: 3–40 латинских букв, цифр или символов _.')
    if not 8 <= len(password) <= 128:
        raise ValueError('Пароль: от 8 до 128 символов.')
    init_database(database_path)
    with database(database_path) as connection:
        connection.execute('INSERT INTO admins(username,password_hash) VALUES (?,?)',
                           (username, generate_password_hash(password)))
        connection.commit()


def minute_value(value):
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def available_starts(connection, service_id, master_id, visit_date, exclude_id=None):
    duration = SERVICE_MAP[service_id]['duration']
    today = salon_now()
    # Старые заявки без специалиста и времени требуют ручного уточнения.
    existing = connection.execute('''SELECT id,service,visit_time FROM bookings
        WHERE master=? AND visit_date=? AND status != 'cancelled' AND visit_time != '' ''',
        (master_id, visit_date)).fetchall()
    starts = []
    for minute in range(10 * 60, 18 * 60 + 1, 30):
        if minute + duration > 19 * 60:
            continue
        if visit_date == today.date().isoformat() and minute <= today.hour * 60 + today.minute:
            continue
        overlap = False
        for row in existing:
            if row['id'] == exclude_id:
                continue
            try:
                other_start = minute_value(row['visit_time'])
            except (ValueError, AttributeError):
                continue
            other_end = other_start + SERVICE_MAP.get(row['service'], {'duration': 60})['duration']
            if minute < other_end and minute + duration > other_start:
                overlap = True
                break
        if not overlap:
            starts.append(f'{minute // 60:02d}:{minute % 60:02d}')
    return starts


def calendar_errors(service_id, master_id, visit_date):
    errors = {}
    if service_id not in SERVICE_MAP:
        errors['service'] = 'Выберите услугу из каталога.'
    if master_id not in MASTER_MAP:
        errors['master'] = 'Выберите специалиста.'
    elif service_id not in MASTER_MAP[master_id]['services']:
        errors['master'] = 'Этот специалист не выполняет выбранную услугу.'
    try:
        chosen = date.fromisoformat(visit_date)
        if chosen.isoformat() != visit_date or not 0 <= (chosen - salon_now().date()).days <= 60:
            raise ValueError
    except (ValueError, TypeError):
        errors['visit_date'] = 'Выберите дату от сегодня до 60 дней вперёд.'
    return errors


def create_app(test_config=None):
    application = Flask(__name__)
    application.config.update(
        DATABASE=os.environ.get('MIRA_DATABASE', str(Path(application.instance_path) / 'beauty.sqlite3')),
        MAX_CONTENT_LENGTH=16 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('MIRA_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    )
    if test_config:
        application.config.update(test_config)
    if not application.config.get('SECRET_KEY'):
        secret = os.environ.get('MIRA_SECRET_KEY')
        if not secret:
            secret_path = Path(application.instance_path) / '.session-secret'
            secret_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
                    file.write(secrets.token_hex(32))
            except FileExistsError:
                pass
            secret = secret_path.read_text(encoding='utf-8').strip()
        application.config['SECRET_KEY'] = secret
    init_database(application.config['DATABASE'])

    def db():
        return database(application.config['DATABASE'])

    def csrf():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return session['csrf_token']

    def limited(scope, limit, seconds):
        identity = hashlib.sha256((scope + '|' + (request.remote_addr or '')).encode()).hexdigest()
        now = time.time()
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT hits,reset_at FROM rate_limits WHERE key=?', (identity,)).fetchone()
            if row and row['reset_at'] > now:
                if row['hits'] >= limit:
                    connection.rollback()
                    return True
                connection.execute('UPDATE rate_limits SET hits=hits+1 WHERE key=?', (identity,))
            else:
                connection.execute('INSERT OR REPLACE INTO rate_limits VALUES (?,?,?)', (identity, 1, now + seconds))
            connection.commit()
        return False

    @application.before_request
    def protect_requests():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected = session.get('csrf_token', '')
            supplied = request.headers.get('X-CSRFToken') or request.form.get('csrf_token', '')
            if not expected or not isinstance(supplied, str) or not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
                if request.path.startswith('/api/'):
                    return jsonify(message='Сессия формы истекла. Обновите страницу и повторите действие.'), 403
                return render_template('error.html', code=403, title='Обновите страницу',
                                       message='Сессия формы истекла. Вернитесь к форме и повторите действие.'), 403

    @application.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        if request.path.startswith(('/admin', '/login', '/api/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @application.template_filter('salon_time')
    def salon_time_filter(value):
        try:
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return timestamp.astimezone(SALON_TZ).strftime('%d.%m.%Y %H:%M')
        except (ValueError, TypeError):
            return value

    @application.context_processor
    def template_context():
        return dict(services=SERVICES, masters=MASTERS, gallery=GALLERY,
                    service_by_id=SERVICE_MAP, master_by_id=MASTER_MAP,
                    csrf_token=csrf(), current_year=salon_now().year,
                    status_labels=STATUS_LABELS, is_admin=bool(session.get('admin_id')))

    @application.get('/')
    def home():
        return render_template('index.html')

    @application.get('/services')
    def services_page():
        return render_template('services.html')

    @application.get('/masters')
    def masters_page():
        return render_template('masters.html')

    @application.get('/gallery')
    def gallery_page():
        return render_template('gallery.html')

    @application.get('/about')
    def about_page():
        return render_template('about.html')

    @application.get('/privacy')
    def privacy_page():
        return render_template('privacy.html')

    @application.get('/booking')
    def booking_page():
        selected_service = request.args.get('service', '')
        selected_master = request.args.get('master', '')
        if selected_service not in SERVICE_MAP:
            selected_service = ''
        if selected_master not in MASTER_MAP:
            selected_master = ''
        if selected_master and not selected_service:
            selected_service = MASTER_MAP[selected_master]['services'][0]
        if selected_master and selected_service and selected_service not in MASTER_MAP[selected_master]['services']:
            selected_master = ''
        return render_template('booking.html', selected_service=selected_service,
            selected_master=selected_master, today=salon_now().date().isoformat(),
            last_day=(salon_now().date() + timedelta(days=60)).isoformat())

    @application.get('/api/csrf')
    def csrf_api():
        return jsonify(csrf_token=csrf())

    @application.get('/api/health')
    def health():
        with db() as connection:
            connection.execute('SELECT 1').fetchone()
        return jsonify(ok=True)

    @application.get('/api/services')
    def services_api():
        return jsonify(SERVICES)

    @application.get('/api/masters')
    def masters_api():
        service_id = request.args.get('service', '')
        return jsonify([item for item in MASTERS if not service_id or service_id in item['services']])

    @application.get('/api/availability')
    def availability():
        service_id = request.args.get('service', '')
        master_id = request.args.get('master', '')
        visit_date = request.args.get('date', '')
        errors = calendar_errors(service_id, master_id, visit_date)
        if errors:
            return jsonify(message='Проверьте услугу, специалиста и дату.', errors=errors), 422
        with db() as connection:
            slots = available_starts(connection, service_id, master_id, visit_date)
        return jsonify(slots=slots, duration=SERVICE_MAP[service_id]['duration'])

    @application.post('/api/bookings')
    def create_booking():
        if limited('booking', 20, 600):
            return jsonify(message='Слишком много заявок. Подождите 10 минут.'), 429
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(message='Ожидается JSON-объект с данными формы.'), 400
        fields = {key: payload[key].strip() if isinstance(payload.get(key), str) else ''
                  for key in ('name', 'phone', 'service', 'master', 'visit_date', 'visit_time', 'comment')}
        errors = calendar_errors(fields['service'], fields['master'], fields['visit_date'])
        if not 2 <= len(fields['name']) <= 60:
            errors['name'] = 'Имя должно содержать от 2 до 60 символов.'
        digits = re.sub(r'\D', '', fields['phone'])
        if not re.fullmatch(r'\+?[0-9 ()-]{10,25}', fields['phone']) or not 10 <= len(digits) <= 15:
            errors['phone'] = 'Укажите телефон: от 10 до 15 цифр.'
        if not re.fullmatch(r'(?:1[0-8]):(?:00|30)', fields['visit_time']):
            errors['visit_time'] = 'Выберите свободное время из списка.'
        if len(fields['comment']) > 500:
            errors['comment'] = 'Комментарий: не более 500 символов.'
        if payload.get('consent') is not True:
            errors['consent'] = 'Необходимо согласие на обработку данных.'
        if errors:
            return jsonify(message='Проверьте поля формы.', errors=errors), 422
        booking_id = uuid.uuid4().hex[:12].upper()
        with db() as connection:
            # Проверка и запись выполняются в одной транзакции: два запроса
            # не смогут занять пересекающееся время у одного специалиста.
            connection.execute('BEGIN IMMEDIATE')
            slots = available_starts(connection, fields['service'], fields['master'], fields['visit_date'])
            if fields['visit_time'] not in slots:
                connection.rollback()
                return jsonify(message='Это время уже недоступно. Выберите другой свободный интервал.'), 409
            connection.execute('''INSERT INTO bookings
                (id,name,phone,service,visit_date,created_at,master,visit_time,comment,status)
                VALUES (?,?,?,?,?,?,?,?,?,'new')''',
                (booking_id, fields['name'], fields['phone'], fields['service'], fields['visit_date'],
                 datetime.now(timezone.utc).isoformat(), fields['master'], fields['visit_time'], fields['comment']))
            connection.commit()
        return jsonify(id=booking_id, message='Запись создана. Сохраните номер заявки.',
                       booking=dict(service=SERVICE_MAP[fields['service']]['name'],
                                    master=MASTER_MAP[fields['master']]['name'],
                                    date=fields['visit_date'], time=fields['visit_time'])), 201

    @application.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('admin_id'):
            return redirect(url_for('admin'))
        error = None
        code = 200
        if request.method == 'POST':
            if limited('login', 10, 900):
                return render_template('login.html', error='Слишком много попыток. Повторите через 15 минут.'), 429
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            with db() as connection:
                row = connection.execute('SELECT * FROM admins WHERE username=?', (username,)).fetchone()
            if row and len(password) <= 128 and check_password_hash(row['password_hash'], password):
                session.clear()
                session['admin_id'] = row['id']
                session['admin_username'] = row['username']
                session.permanent = True
                csrf()
                return redirect(url_for('admin'))
            error = 'Неверный логин или пароль.'
            code = 401
        return render_template('login.html', error=error), code

    def admin_required():
        if not session.get('admin_id'):
            return redirect(url_for('login'))
        with db() as connection:
            exists = connection.execute('SELECT 1 FROM admins WHERE id=?', (session['admin_id'],)).fetchone()
        if not exists:
            session.clear()
            return redirect(url_for('login'))
        return None

    @application.get('/admin')
    def admin():
        denied = admin_required()
        if denied is not None:
            return denied
        status = request.args.get('status', '')
        if status not in STATUS_LABELS:
            status = ''
        query = request.args.get('q', '').strip()[:80]
        sql = 'SELECT * FROM bookings WHERE 1=1'
        params = []
        if status:
            sql += ' AND status=?'
            params.append(status)
        if query:
            sql += ' AND (name LIKE ? OR phone LIKE ? OR id LIKE ?)'
            params.extend(['%' + query + '%'] * 3)
        sql += ' ORDER BY visit_date DESC, visit_time DESC, created_at DESC'
        with db() as connection:
            rows = [dict(row) for row in connection.execute(sql, params)]
            counts = {key: 0 for key in STATUS_LABELS}
            for item in connection.execute('SELECT status,count(*) AS n FROM bookings GROUP BY status'):
                counts[item['status']] = item['n']
        counts['total'] = sum(counts.values())
        return render_template('admin.html', bookings=rows, counts=counts, status_filter=status, query=query)

    @application.post('/admin/bookings/<booking_id>/status')
    def admin_status(booking_id):
        denied = admin_required()
        if denied is not None:
            return denied
        status = request.form.get('status', '')
        if status not in STATUS_LABELS:
            return render_template('error.html', code=422, title='Неизвестный статус', message='Выберите статус из списка.'), 422
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
            if row is None:
                connection.rollback()
                return render_template('error.html', code=404, title='Заявка не найдена', message='Проверьте номер заявки.'), 404
            if (row['status'] == 'cancelled' and status != 'cancelled'
                    and row['service'] in SERVICE_MAP and row['master'] in MASTER_MAP and row['visit_time']):
                slots = available_starts(connection, row['service'], row['master'], row['visit_date'], row['id'])
                if row['visit_time'] not in slots:
                    connection.rollback()
                    flash('Время уже занято. Восстановить отменённую запись нельзя.', 'error')
                    return redirect(url_for('admin'))
            connection.execute('UPDATE bookings SET status=? WHERE id=?', (status, booking_id))
            connection.commit()
        flash('Статус заявки обновлён.', 'success')
        return redirect(url_for('admin'))

    @application.get('/admin/export.csv')
    def admin_export():
        denied = admin_required()
        if denied is not None:
            return denied
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Номер', 'Имя', 'Телефон', 'Услуга', 'Мастер', 'Дата', 'Время', 'Статус', 'Комментарий'])
        with db() as connection:
            rows = connection.execute('SELECT * FROM bookings ORDER BY created_at DESC').fetchall()
        for row in rows:
            values = [row['id'], row['name'], row['phone'], SERVICE_MAP.get(row['service'], {'name': row['service']})['name'],
                      MASTER_MAP.get(row['master'], {'name': 'Уточнить'})['name'], row['visit_date'], row['visit_time'],
                      STATUS_LABELS.get(row['status'], row['status']), row['comment']]
            writer.writerow(["'" + str(value) if str(value).lstrip().startswith(('=', '+', '-', '@')) else value for value in values])
        return Response(('\ufeff' + output.getvalue()).encode('utf-8'), content_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=mira-bookings.csv'})

    @application.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))

    @application.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/api/'):
            return jsonify(message='Маршрут не найден.'), 404
        return render_template('error.html', code=404, title='Страница не найдена', message='Воспользуйтесь меню или вернитесь на главную.'), 404

    @application.errorhandler(413)
    def too_large(error):
        return jsonify(message='Слишком большой запрос.'), 413

    @application.errorhandler(sqlite3.Error)
    def db_error(error):
        application.logger.error('Database operation failed: %s', type(error).__name__)
        if request.path.startswith('/api/'):
            return jsonify(message='Хранилище временно недоступно. Повторите позже.'), 503
        return render_template('error.html', code=503, title='Попробуйте чуть позже', message='Не удалось выполнить операцию с данными.'), 503

    @application.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', code=500, title='Не удалось открыть страницу', message='Попробуйте обновить страницу позже.'), 500

    return application


app = create_app()
DB = Path(app.config['DATABASE'])


def setup_admin(force=False):
    with database(DB) as connection:
        if not force and connection.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            print('Администратор уже создан. Используйте свой логин и пароль на /login.')
            return
    print('Создание администратора. Пароль при вводе не отображается.')
    username = input('Логин [admin]: ').strip() or 'admin'
    password = getpass.getpass('Пароль (минимум 8 символов): ')
    confirmation = getpass.getpass('Повторите пароль: ')
    if password != confirmation:
        raise ValueError('Пароли не совпадают.')
    create_admin(username, password, DB)
    print('Администратор создан. Запомните введённые логин и пароль.')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('setup-admin', 'create-admin'):
        try:
            setup_admin(force=sys.argv[1] == 'create-admin')
        except (ValueError, sqlite3.IntegrityError) as error:
            print(f'Не удалось создать администратора: {error}')
            sys.exit(1)
    else:
        from waitress import serve
        host = os.environ.get('MIRA_HOST', '127.0.0.1')
        port = int(os.environ.get('MIRA_PORT', '5000'))
        local_url = f'http://127.0.0.1:{port}'
        print(f'Mira Beauty: {local_url}', flush=True)
        print('Остановка сервера: Ctrl+C', flush=True)
        if os.environ.get('MIRA_OPEN_BROWSER') == '1':
            threading.Timer(1.5, lambda: webbrowser.open(local_url)).start()
        serve(app, host=host, port=port, threads=4)
