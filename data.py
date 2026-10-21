"""Демонстрационные услуги, специалисты и иллюстрации Mira Beauty."""
SERVICES = [
    dict(id='hair', name='Стрижка и укладка', price=7000, duration=60, time='60 минут', category='Волосы', description='Подберём форму, которая подчеркнёт ваш характер. Мытьё, стрижка и лёгкая укладка включены.', image='service-hair.svg'),
    dict(id='color', name='Окрашивание волос', price=18000, duration=180, time='180 минут', category='Волосы', description='Новый оттенок и бережная работа с цветом. В учебном каталоге указана демонстрационная стоимость.', image='service-color.svg'),
    dict(id='nails', name='Маникюр с покрытием', price=6000, duration=90, time='90 минут', category='Ногти', description='Аккуратная форма, уход за кутикулой и однотонное покрытие в вашем любимом оттенке.', image='service-nails.svg'),
    dict(id='makeup', name='Вечерний макияж', price=9000, duration=60, time='60 минут', category='Макияж', description='Выразительный образ для особенного события с вниманием к вашему стилю и пожеланиям.', image='service-makeup.svg'),
    dict(id='brows', name='Оформление бровей', price=4000, duration=40, time='40 минут', category='Уход', description='Подбор формы, мягкая коррекция и окрашивание для естественного, ухоженного результата.', image='service-brows.svg'),
    dict(id='care', name='Уход за лицом', price=11000, duration=60, time='60 минут', category='Уход', description='Спокойный ритуал: мягкое очищение и увлажняющий уход. Без медицинских процедур.', image='service-care.svg'),
]
MASTERS = [
    dict(id='amina', name='Амина', role='Стилист по волосам', bio='Любит естественные линии, мягкие переходы цвета и образы, с которыми легко каждый день.', experience='Стрижки и окрашивание', services=['hair', 'color'], image='master-amina.svg'),
    dict(id='dana', name='Дана', role='Мастер маникюра и бровей', bio='Внимательна к деталям: от аккуратной формы ногтей до гармоничной линии бровей.', experience='Маникюр и оформление бровей', services=['nails', 'brows'], image='master-dana.svg'),
    dict(id='sofia', name='София', role='Визажист и специалист по уходу', bio='Считает, что выразительный макияж и бережный уход начинаются с понимания ваших пожеланий.', experience='Макияж и уход за лицом', services=['makeup', 'care'], image='master-sofia.svg'),
]
GALLERY = [
    dict(id='bob', title='Чистые линии', category='Волосы', image='gallery-bob.svg'),
    dict(id='color', title='Мягкий медный оттенок', category='Волосы', image='gallery-color.svg'),
    dict(id='nails', title='Нюд и маленький акцент', category='Ногти', image='gallery-nails.svg'),
    dict(id='makeup', title='Тёплое вечернее сияние', category='Макияж', image='gallery-makeup.svg'),
    dict(id='brows', title='Естественная форма', category='Уход', image='gallery-brows.svg'),
    dict(id='care', title='Ритуал спокойствия', category='Уход', image='gallery-care.svg'),
]
STATUS_LABELS = {'new': 'Новая', 'confirmed': 'Подтверждена', 'completed': 'Завершена', 'cancelled': 'Отменена'}
