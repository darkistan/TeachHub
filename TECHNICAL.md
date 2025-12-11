# 🔧 Технічна документація - Schedule Bot v2.0

Детальна технічна інформація для розробників та адміністраторів.

---

## 📁 Структура проекту

```
schedule_bot/
├── 🚀 Запуск
│   ├── setup.bat              # Налаштування
│   ├── start_all.bat          # Запуск всього
│   ├── start_bot.bat          # Тільки бот
│   ├── start_web.bat          # Тільки веб
│   ├── bot.py                 # Telegram бот (1485 рядків)
│   └── run_web.py             # Flask запуск
│
├── 💾 База даних
│   ├── models.py              # 10 SQLAlchemy моделей
│   ├── database.py            # Управління БД + WAL
│   └── schedule_bot.db        # SQLite БД
│
├── 🔧 Модулі бота
│   ├── auth.py                # Авторизація (БД)
│   ├── schedule_handler.py    # Розклад (БД + кеш)
│   ├── notification_manager.py # Оповіщення (БД)
│   ├── announcement_manager.py # Оголошення (БД)
│   ├── schedule_analyzer.py   # Аналіз навчання
│   ├── air_alert.py           # API тривог
│   ├── logger.py              # Логування (БД + файл)
│   ├── csrf_manager.py        # CSRF захист
│   └── input_validator.py     # Валідація
│
├── 🌐 Веб-інтерфейс
│   └── web_admin/
│       ├── app.py             # Flask (450+ рядків, 20+ маршрутів)
│       ├── templates/         # 8 HTML шаблонів
│       │   ├── base.html      # Bootstrap 5 + тема + тривога
│       │   ├── dashboard.html # Статистика
│       │   ├── users.html     # CRUD користувачі
│       │   ├── schedule.html  # CRUD розклад
│       │   ├── announcements.html # CRUD оголошення
│       │   ├── academic.html  # CRUD періоди
│       │   ├── logs.html      # Фільтри
│       │   ├── settings.html  # Налаштування
│       │   └── stats.html     # Аналітика
│       └── static/
│           ├── css/style.css  # Темна/світла тема
│           └── js/main.js     # Тема + тривога
│
└── ⚙️ Конфігурація
    ├── config.env.example     # Шаблон
    ├── .gitignore            # Git захист
    └── requirements.txt       # Залежності
```

---

## 🗄️ Архітектура бази даних

### Моделі (models.py):

**User** - користувачі
```python
user_id (Integer, unique)
username (String)
approved_at (DateTime)
notifications_enabled (Boolean)
```

**ScheduleEntry** - заняття
```python
day_of_week, time, subject
lesson_type, teacher, teacher_phone
classroom, conference_link
exam_type, week_type
```

**ScheduleMetadata** - метадані
```python
current_week (numerator/denominator)
group_name, academic_year
numerator_start_date
```

**AcademicPeriod** - періоди навчання
```python
period_id, name
start_date, end_date, weeks
color, description
```

**Announcement** - оголошення
```python
content, author_id, author_username
priority, created_at, updated_at
is_active
```

**NotificationHistory** - історія оповіщень
```python
user_id, lesson_key
sent_at, notification_date
```

**Log** - системні логи
```python
timestamp, level, message
user_id, command
```

**BotConfig** - конфігурація
```python
key, value, description
```

---

## 🔒 Конкурентний доступ (веб + бот)

### Проблема:
SQLite блокується при одночасному запису

### Рішення:

**1. WAL Mode (Write-Ahead Logging)**
```python
PRAGMA journal_mode=WAL
```
- Читання НЕ блокує запис
- Запис НЕ блокує читання

**2. Busy Timeout (30 секунд)**
```python
PRAGMA busy_timeout=30000
```
- При блокуванні чекає 30с замість помилки

**3. Retry Logic (3 спроби)**
```python
with get_session(max_retries=3) as session:
    # Автоматичний retry з exponential backoff
```

**4. Connection Pool**
```python
pool_size=10, max_overflow=20  # До 30 з'єднань
```

**5. Оптимізація**
```python
PRAGMA cache_size=10000     # 10MB кеш
PRAGMA synchronous=NORMAL   # Баланс
```

### Перевірка:
База даних автоматично налаштовується при запуску бота через `database.py`.

---

## 🌐 Flask веб-інтерфейс

### Архітектура (app.py):

**Маршрути (20+):**

**Dashboard:**
- `GET /` - статистика, метадані, останні логи

**Користувачі:**
- `GET /users` - список + запити
- `POST /users/add` - додати
- `POST /users/delete/<id>` - видалити
- `POST /users/approve/<id>` - схвалити
- `POST /users/deny/<id>` - відхилити

**Розклад:**
- `GET /schedule` - перегляд (tabs по днях)
- `POST /schedule/add` - додати заняття
- `POST /schedule/edit/<id>` - редагувати
- `POST /schedule/delete/<id>` - видалити

**Оголошення:**
- `GET /announcements` - список + активне
- `POST /announcements/create` - створити
- `POST /announcements/edit/<id>` - редагувати
- `POST /announcements/delete/<id>` - видалити
- `POST /announcements/activate/<id>` - активувати

**Академічний календар:**
- `GET /academic` - періоди + timeline
- `POST /academic/add` - додати період
- `POST /academic/edit/<id>` - редагувати
- `POST /academic/delete/<id>` - видалити

**Системні:**
- `GET /logs` - логи з фільтрами
- `GET /settings` - налаштування
- `POST /settings/update` - оновити
- `GET /stats` - статистика
- `GET /api/alert-status` - API тривоги (JSON)

### Безпека:

**CSRF Protection:**
```python
from flask_wtf import CSRFProtect
csrf = CSRFProtect(app)

# У формах:
<input type="hidden" name="csrf_token" value="{{csrf_token()}}"/>
```

**API Endpoint (без CSRF):**
```python
@app.route('/api/alert-status')
@csrf.exempt
def api_alert_status():
    # Публічний API для AJAX
```

---

## 🎨 Темна тема

### Реалізація (Bootstrap 5):

**HTML:**
```html
<html data-bs-theme="light">
```

**JavaScript (main.js):**
```javascript
// Зміна теми
document.documentElement.setAttribute('data-bs-theme', 'dark');

// Збереження
localStorage.setItem('theme', 'dark');

// Іконка
icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
```

**CSS (style.css):**
```css
[data-bs-theme="dark"] body {
    background-color: #1a1d20;
    color: #f8f9fa;
}

[data-bs-theme="dark"] .card {
    background-color: #2b3035;
}
```

### Адаптовані компоненти:
- Cards, tables, forms
- Modals, tabs, navbar
- Buttons, badges, alerts

---

## 🚨 Статус повітряної тривоги

### API Інтеграція:

**Backend (app.py):**
```python
@app.route('/api/alert-status')
def api_alert_status():
    air_alert_manager = get_air_alert_manager()
    alert_status = await air_alert_manager.get_alert_status()
    
    return jsonify({
        'alert': bool,
        'message': str,
        'types': list
    })
```

**Frontend (main.js):**
```javascript
async function updateAlertStatus() {
    const response = await fetch('/api/alert-status');
    const data = await response.json();
    
    // Оновлюємо badge
    if (data.alert) {
        // Червоний з пульсацією
    } else {
        // Зелений
    }
}

// Автооновлення кожну хвилину
setInterval(updateAlertStatus, 60000);
```

**Анімація (style.css):**
```css
@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.6; }
    100% { opacity: 1; }
}

.pulse-animation {
    animation: pulse 2s ease-in-out infinite;
}
```

---

## 🔧 Розробка

### Додавання нової моделі БД:

```python
# models.py
class NewModel(Base):
    __tablename__ = 'new_table'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))

# Використання
from database import get_session
from models import NewModel

with get_session() as session:
    item = NewModel(name="Test")
    session.add(item)
    session.commit()
```

### Додавання нового маршруту Flask:

```python
# web_admin/app.py
@app.route('/new-page')
def new_page():
    with get_session() as session:
        data = session.query(Model).all()
        return render_template('new_page.html', data=data)
```

### Додавання сторінки HTML:

```html
<!-- web_admin/templates/new_page.html -->
{% extends "base.html" %}
{% block title %}New Page{% endblock %}
{% block content %}
  <h1>New Page</h1>
{% endblock %}
```

---

## 🛠️ Утиліти


## 📊 Залежності

**Python пакети (requirements.txt):**
```
python-telegram-bot==21.7    # Telegram API
python-dotenv==1.0.0         # .env файли
sqlalchemy>=2.0.35           # ORM для БД
flask==3.0.0                 # Веб framework
flask-wtf==1.2.1             # CSRF захист
alembic==1.13.0              # Міграції БД (опціонально)
```

**Сумісність:**
- Python: 3.8 - 3.13
- SQLite: 3.35+
- Windows: 10/11
- Linux/Mac: підтримується

---

## 🔐 Файл config.env

**Структура:**
```env
# Telegram
TELEGRAM_BOT_TOKEN=7946502371:AAE...    # Обов'язково
# ADMIN_USER_ID більше не використовується - адміністрація тільки через веб-інтерфейс

# База даних
DATABASE_URL=sqlite:///schedule_bot.db  # Опціонально

# Тривоги
AIR_ALERT_CITY=Дніпро                  # Опціонально
ALERTS_API_TOKEN=fcf3d777...           # Опціонально

# Flask
FLASK_SECRET_KEY=random-secret-key     # Опціонально
```

**Де взяти токени:**
- `TELEGRAM_BOT_TOKEN` - @BotFather в Telegram
- `ADMIN_USER_ID` - більше не використовується (адміністрація тільки через веб-інтерфейс)
- `ALERTS_API_TOKEN` - https://alerts.in.ua/

---

## 🔄 Синхронізація веб ↔ бот

### Як працює:

1. **Веб змінює дані** → SQLite БД
2. **Бот читає з БД** → Показує користувачам
3. **WAL mode** → Без блокувань

### Приклад:

```
Адмін через веб:
  /schedule/add → Додає заняття → БД

Користувач в Telegram:
  /today → Читає з БД → Бачить нове заняття
```

**Затримка:** < 1 секунда (кеш 60с в schedule_handler)

---

## 🧪 Тестування

### Перевірка БД:
```python
from database import init_database, get_session
from models import User, ScheduleEntry

init_database()

with get_session() as session:
    users = session.query(User).count()
    schedule = session.query(ScheduleEntry).count()
    print(f"Users: {users}, Schedule: {schedule}")
```

### Тест API тривоги:
```python
from air_alert import get_air_alert_manager
import asyncio

async def test():
    manager = get_air_alert_manager()
    status = await manager.get_alert_status()
    print(f"Alert: {status}")

asyncio.run(test())
```

### Тест веб:
```batch
venv\Scripts\python.exe run_web.py
# Відкрити: http://127.0.0.1:5000
```

---

## 🐛 Troubleshooting

### Помилка "database is locked"

**Діагностика:**
```batch
```

**Рішення 1 - Увімкнути WAL:**
```batch
```

**Рішення 2 - Перезапустити:**
```batch
# Зупиніть бота та веб (Ctrl+C)
# Запустіть знову
start_all.bat
```

**Рішення 3 - Checkpoint:**
```batch

---

### Помилка "weak reference to 'Application'"

**Причина:** Несумісність python-telegram-bot з Python 3.13

**Рішення:**
```batch
venv\Scripts\python.exe -m pip install "python-telegram-bot==21.7"
```

---

### Кракозябри в консолі Windows

**Причина:** Українські символи та emoji в Windows консолі

**Рішення:** Це нормально! 
- Бот працює коректно
- В Telegram все виглядає правильно
- Веб-інтерфейс без проблем

**Альтернатива:**
- Використовуйте Windows Terminal (підтримує UTF-8)
- Або дивіться логи через веб: http://127.0.0.1:5000/logs

---

### Помилка при імпорті модуля

**Симптом:**
```
ModuleNotFoundError: No module named 'schedule_handler_db'
```

**Рішення:**
Перевірте що використовуються правильні імпорти:
```python
# Правильно:
from schedule_handler import get_schedule_handler
from auth import auth_manager

# Неправильно (старі назви):
from schedule_handler_db import ...
from auth_db import ...
```

---

## 📈 Продуктивність

### Кешування:

**ScheduleHandler:**
- Кеш розкладу на 60 секунд
- Інвалідація при зміні даних
- Зменшує навантаження на БД

**Connection Pool:**
- 10 постійних з'єднань
- До 30 з'єднань загалом
- Автоматичне перевикористання

### Оптимізація PRAGMA:
```sql
PRAGMA journal_mode=WAL       -- Конкурентність
PRAGMA cache_size=10000       -- 10MB кеш
PRAGMA synchronous=NORMAL     -- Баланс
PRAGMA busy_timeout=30000     -- 30s timeout
```

---

## 🔄 Backup та відновлення

### Створення backup:
```batch
copy schedule_bot.db backup\schedule_bot_%date%.db
```

### Відновлення:
```batch
copy backup\schedule_bot_YYYYMMDD.db schedule_bot.db
```

### Автоматичний backup (через database.py):
```python
from database import get_db_manager

db = get_db_manager()
db.backup_database('backup/auto_backup.db')
```

---

## 🌐 API Endpoints

### GET `/api/alert-status`

**Response (тихо):**
```json
{
  "alert": false,
  "message": "ТИХО в Дніпро",
  "city": "Дніпро"
}
```

**Response (тривога):**
```json
{
  "alert": true,
  "message": "ТРИВОГА в Дніпро!",
  "city": "Дніпро",
  "types": ["air_raid"]
}
```

**CSRF:** Exempt (публічний API для AJAX)

**Використання:**
```javascript
fetch('/api/alert-status')
  .then(r => r.json())
  .then(data => console.log(data.message));
```

---

## 🎨 Кастомізація

### Зміна кольорів теми:

**style.css:**
```css
/* Light theme */
[data-bs-theme="light"] body {
    background-color: #your-color;
}

/* Dark theme */
[data-bs-theme="dark"] body {
    background-color: #your-dark-color;
}
```

### Додавання нової іконки Bootstrap:

```html
<i class="bi bi-icon-name"></i>
```

**Список:** https://icons.getbootstrap.com/

---

## 📊 Статистика проекту

**Код:**
- Python: ~8,000 рядків
- HTML: ~1,500 рядків
- JavaScript: ~200 рядків
- CSS: ~150 рядків

**Файли:**
- Модулі Python: 10
- HTML шаблони: 8
- .bat скрипти: 4
- Утиліти: 2

**База даних:**
- Таблиць: 10
- Індексів: 15+
- Triggers: 0 (SQLAlchemy ORM)

---

## 🔗 Корисні посилання

**Документація:**
- Flask: https://flask.palletsprojects.com/
- SQLAlchemy: https://docs.sqlalchemy.org/
- python-telegram-bot: https://docs.python-telegram-bot.org/
- Bootstrap 5: https://getbootstrap.com/docs/5.3/

**API:**
- alerts.in.ua: https://alerts.in.ua/
- Telegram Bot API: https://core.telegram.org/bots/api

---

**Технічна документація Schedule Bot v2.0** 📚




