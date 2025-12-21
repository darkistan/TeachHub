"""
Flask веб-інтерфейс для управління TeachHub
Адмін панель для управління викладачами, розкладом, оголошеннями тощо
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_wtf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Додаємо батьківську директорію в Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import init_database, get_session
from models import (
    User, PendingRequest, ScheduleEntry, ScheduleMetadata,
    AcademicPeriod, Announcement, AnnouncementRecipient,
    NotificationHistory, NotificationSettings, Log, BotConfig, Group,
    Poll, PollOption, PollResponse
)
from air_alert import get_air_alert_manager
from poll_manager import get_poll_manager
from logger import logger

# Завантажуємо змінні середовища
load_dotenv("config.env")

# Telegram Bot API для відправки повідомлень
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None
DEVELOPER_TELEGRAM_ID = os.getenv("DEVELOPER_TELEGRAM_ID")

# Перевірка режиму роботи
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true' if FLASK_ENV == 'development' else False

# Ініціалізація Flask
app = Flask(__name__)
app.config['ENV'] = FLASK_ENV
app.config['DEBUG'] = FLASK_DEBUG and FLASK_ENV == 'development'
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['WTF_CSRF_ENABLED'] = True

# Валідація SECRET_KEY для production
if FLASK_ENV == 'production':
    if app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
        import warnings
        warnings.warn(
            "⚠️ ВИКОРИСТОВУЄТЬСЯ DEV SECRET KEY В PRODUCTION! "
            "Згенеруйте новий ключ: openssl rand -hex 32",
            UserWarning
        )
        logger.log_error("КРИТИЧНО: Використовується dev SECRET_KEY в production!")

# Налаштування для Cloudflare (ProxyFix для правильної обробки X-Forwarded-For)
# Це дозволяє Flask правильно визначати IP клієнтів через Cloudflare
if FLASK_ENV == 'production':
    # ProxyFix обробляє заголовки X-Forwarded-For, X-Forwarded-Proto від Cloudflare
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,      # Кількість проксі перед сервером (Cloudflare = 1)
        x_proto=1,    # Обробка X-Forwarded-Proto (HTTP/HTTPS)
        x_host=1,     # Обробка X-Forwarded-Host
        x_port=1      # Обробка X-Forwarded-Port
    )

# CSRF захист
csrf = CSRFProtect(app)

# Ініціалізація Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Будь ласка, увійдіть для доступу до цієї сторінки.'
login_manager.login_message_category = 'info'

# Ініціалізація Flask-Limiter для rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Ініціалізація БД при запуску
init_database()


# Security Headers
@app.after_request
def set_security_headers(response):
    """Додавання security headers до всіх відповідей"""
    # Запобігання MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Запобігання clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # XSS Protection (застарілий, але все ще підтримується)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Content Security Policy (базовий)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    # Strict Transport Security (тільки якщо використовується HTTPS)
    if request.is_secure or os.getenv('FLASK_ENV') == 'production':
        # HSTS тільки для production з HTTPS
        hsts_max_age = 31536000  # 1 рік
        response.headers['Strict-Transport-Security'] = f'max-age={hsts_max_age}; includeSubDomains; preload'
    
    return response


# Context processor для передачі metadata у всі шаблони
@app.context_processor
def inject_metadata():
    """Додає metadata до всіх шаблонів"""
    try:
        with get_session() as session:
            metadata = session.query(ScheduleMetadata).first()
            if metadata:
                # Витягуємо значення всередині сесії, щоб уникнути DetachedInstanceError
                academic_year = metadata.academic_year
                return dict(global_metadata={'academic_year': academic_year})
            return dict(global_metadata=None)
    except Exception:
        return dict(global_metadata=None)


# Клас для Flask-Login
class WebUser(UserMixin):
    """Обгортка для User моделі для Flask-Login"""
    def __init__(self, user: User):
        # Зберігаємо всі необхідні дані безпосередньо, щоб не залежати від сесії
        self.id = user.user_id
        self._user_id = user.user_id
        self._role = user.role
        self._full_name = user.full_name
        self._username = user.username
        self._can_edit_schedule = getattr(user, 'can_edit_schedule', True)
        self._can_edit_academic = getattr(user, 'can_edit_academic', True)
    
    def get_id(self):
        return str(self._user_id)
    
    @property
    def is_admin(self):
        return self._role == 'admin'
    
    @property
    def user_id(self):
        return self._user_id
    
    @property
    def full_name(self):
        return self._full_name or self._username or f"ID: {self._user_id}"
    
    @property
    def can_edit_schedule(self):
        # Адміністратори завжди мають права
        if self.is_admin:
            return True
        return self._can_edit_schedule
    
    @property
    def can_edit_academic(self):
        # Адміністратори завжди мають права
        if self.is_admin:
            return True
        return self._can_edit_academic


@login_manager.user_loader
def load_user(user_id_str):
    """Завантаження користувача для Flask-Login"""
    try:
        user_id = int(user_id_str)
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user and user.password_hash:  # Тільки користувачі з паролем можуть входити
                return WebUser(user)
    except (ValueError, TypeError):
        pass
    return None


def admin_required(f):
    """Декоратор для перевірки прав адміністратора"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Доступ заборонено. Потрібні права адміністратора.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """Сторінка входу з rate limiting (5 спроб на хвилину)"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Отримуємо список користувачів з паролями для вибору
    with get_session() as session:
        users_with_passwords = session.query(User).filter(
            User.password_hash.isnot(None)
        ).order_by(User.full_name, User.username).all()
        
        # Формуємо список для dropdown
        users_list = []
        for user in users_with_passwords:
            display_name = user.full_name if user.full_name else (user.username or f"ID: {user.user_id}")
            if user.role == 'admin':
                display_name += " (Адмін)"
            users_list.append({
                'user_id': user.user_id,
                'display_name': display_name
            })
    
    if request.method == 'POST':
        user_id_str = request.form.get('user_id', '').strip()
        password = request.form.get('password', '')
        
        if not user_id_str or not password:
            flash('Будь ласка, виберіть користувача та введіть пароль.', 'warning')
            return render_template('login.html', users=users_list)
        
        try:
            user_id = int(user_id_str)
            with get_session() as session:
                user = session.query(User).filter(User.user_id == user_id).first()
                
                if user and user.password_hash and check_password_hash(user.password_hash, password):
                    web_user = WebUser(user)
                    login_user(web_user, remember=True)
                    
                    # Логування успішного входу
                    logger.log_info(f"Успішний вхід користувача {user.user_id} ({user.full_name or user.username})", user_id=user.user_id)
                    
                    next_page = request.args.get('next')
                    return redirect(next_page) if next_page else redirect(url_for('dashboard'))
                else:
                    # Логування невдалої спроби входу
                    logger.log_warning(f"Невдала спроба входу для користувача {user_id} з IP {get_remote_address()}", user_id=user_id if 'user_id' in locals() else None)
                    flash('Невірний пароль.', 'danger')
        except ValueError:
            flash('Помилка вибору користувача.', 'danger')
        except Exception as e:
            flash(f'Помилка входу: {e}', 'danger')
    
    return render_template('login.html', users=users_list)


@app.route('/health')
def health_check():
    """Health check endpoint для моніторингу"""
    try:
        # Перевірка підключення до БД
        with get_session() as session:
            session.execute("SELECT 1")
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'environment': FLASK_ENV
        }), 200
    except Exception as e:
        logger.log_error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e) if FLASK_ENV == 'development' else 'Internal error',
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/logout')
@login_required
def logout():
    """Вихід з системи"""
    user_id = current_user.user_id
    logout_user()
    logger.log_info(f"Користувач {user_id} вийшов з системи", user_id=user_id)
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    """Головна сторінка - Dashboard"""
    try:
        with get_session() as session:
            # Для користувачів показуємо тільки їх дані
            if current_user.is_admin:
                stats = {
                    'users_count': session.query(User).count(),
                    'pending_requests': session.query(PendingRequest).count(),
                    'schedule_entries': session.query(ScheduleEntry).count(),
                    'announcements_count': session.query(Announcement).count(),
                }
                recent_logs = session.query(Log).order_by(Log.timestamp.desc()).limit(10).all()
            else:
                # Для звичайних користувачів - статистика в годинах та корисна інформація
                # Розраховуємо навантаження в годинах
                workload = calculate_teacher_workload(session, current_user.user_id)
                
                # Отримуємо заняття для чисельника та знаменника окремо
                numerator_entries = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == current_user.user_id,
                    ScheduleEntry.week_type == 'numerator'
                ).count()
                
                denominator_entries = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == current_user.user_id,
                    ScheduleEntry.week_type == 'denominator'
                ).count()
                
                # Розраховуємо навантаження для чисельника та знаменника
                numerator_workload = calculate_teacher_workload_by_week_type(session, current_user.user_id, 'numerator')
                denominator_workload = calculate_teacher_workload_by_week_type(session, current_user.user_id, 'denominator')
                
                # Отримуємо найближчі заняття (сьогодні та завтра)
                # Мапінг днів тижня (Python weekday: 0=Monday, 6=Sunday)
                weekday_map = {
                    0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                    4: 'friday', 5: 'saturday', 6: 'sunday'
                }
                today = datetime.now().date()
                today_weekday = weekday_map[today.weekday()]
                tomorrow = today + timedelta(days=1)
                tomorrow_weekday = weekday_map[tomorrow.weekday()]
                
                # Визначаємо поточний тип тижня
                from schedule_handler import get_schedule_handler
                schedule_handler = get_schedule_handler()
                if schedule_handler:
                    current_week_type = schedule_handler.get_current_week_type()
                else:
                    # Якщо handler не ініціалізований, визначаємо тип тижня безпосередньо з БД
                    # з підтримкою автоматичного визначення через numerator_start_date
                    metadata_for_week = session.query(ScheduleMetadata).first()
                    if metadata_for_week:
                        # Спочатку намагаємося автоматично визначити на основі дати
                        if metadata_for_week.numerator_start_date:
                            try:
                                from schedule_handler import ScheduleHandler
                                temp_handler = ScheduleHandler()
                                auto_week = temp_handler._calculate_week_type_from_date(metadata_for_week.numerator_start_date)
                                if auto_week:
                                    # Оновлюємо current_week в БД для синхронізації
                                    if metadata_for_week.current_week != auto_week:
                                        metadata_for_week.current_week = auto_week
                                        metadata_for_week.last_updated = datetime.now()
                                        session.commit()
                                    current_week_type = auto_week
                                else:
                                    # Якщо автоматичне визначення недоступне, використовуємо збережене значення
                                    current_week_type = metadata_for_week.current_week if metadata_for_week.current_week in ["numerator", "denominator"] else 'numerator'
                            except Exception as e:
                                logger.log_error(f"Помилка автоматичного визначення типу тижня: {e}")
                                current_week_type = metadata_for_week.current_week if metadata_for_week.current_week in ["numerator", "denominator"] else 'numerator'
                        else:
                            # Якщо автоматичне визначення недоступне, використовуємо збережене значення
                            current_week_type = metadata_for_week.current_week if metadata_for_week.current_week in ["numerator", "denominator"] else 'numerator'
                    else:
                        current_week_type = 'numerator'
                
                # Заняття на сьогодні (показуємо заняття для поточного типу тижня)
                today_lessons = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == current_user.user_id,
                    ScheduleEntry.day_of_week == today_weekday,
                    ScheduleEntry.week_type == current_week_type
                ).order_by(ScheduleEntry.time).all()
                
                # Заняття на завтра
                tomorrow_lessons = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == current_user.user_id,
                    ScheduleEntry.day_of_week == tomorrow_weekday,
                    ScheduleEntry.week_type == current_week_type
                ).order_by(ScheduleEntry.time).all()
                
                stats = {
                    'total_hours': workload['total_hours'],
                    'lessons_count': workload['lessons_count'],
                    'numerator_hours': numerator_workload['total_hours'],
                    'numerator_lessons': numerator_workload['lessons_count'],
                    'denominator_hours': denominator_workload['total_hours'],
                    'denominator_lessons': denominator_workload['lessons_count'],
                    'by_day': workload['by_day'],
                    'by_type': workload['by_type'],
                    'today_lessons': today_lessons,
                    'tomorrow_lessons': tomorrow_lessons,
                    'current_week_type': current_week_type
                }
                recent_logs = []
            
            # Метадані розкладу
            metadata = session.query(ScheduleMetadata).first()
            
            return render_template('dashboard.html',
                                 stats=stats,
                                 metadata=metadata,
                                 logs=recent_logs)
    except Exception as e:
        flash(f'Помилка завантаження даних: {e}', 'danger')
        return render_template('dashboard.html', stats={}, metadata=None, logs=[])


@app.route('/users')
@admin_required
def users():
    """Управління користувачами"""
    try:
        with get_session() as session:
            all_users = session.query(User).all()
            pending = session.query(PendingRequest).all()
            
            return render_template('users.html',
                                 users=all_users,
                                 pending_requests=pending,
                                 developer_telegram_id=DEVELOPER_TELEGRAM_ID)
    except Exception as e:
        flash(f'Помилка завантаження користувачів: {e}', 'danger')
        return render_template('users.html', users=[], pending_requests=[], developer_telegram_id=None)


@app.route('/users/add', methods=['POST'])
@admin_required
def add_user():
    """Додавання користувача"""
    try:
        user_id = int(request.form.get('user_id'))
        username = request.form.get('username', 'без username')
        full_name = request.form.get('full_name', '').strip()
        
        with get_session() as session:
            # Перевіряємо чи вже існує
            existing = session.query(User).filter(User.user_id == user_id).first()
            if existing:
                flash('Користувач вже існує!', 'warning')
                return redirect(url_for('users'))
            
            user = User(
                user_id=user_id,
                username=username,
                approved_at=datetime.now(),
                notifications_enabled=False,
                role='user',  # Завжди user для Telegram користувачів
                full_name=full_name if full_name else None
            )
            session.add(user)
            session.commit()
            
            flash(f'Викладача @{username} додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання користувача: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/update-full-name/<int:user_id>', methods=['POST'])
@admin_required
def update_user_full_name(user_id):
    """Оновлення ПІБ викладача та прав доступу"""
    try:
        full_name = request.form.get('full_name', '').strip()
        can_edit_schedule = request.form.get('can_edit_schedule') == '1'
        can_edit_academic = request.form.get('can_edit_academic') == '1'
        
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                # Оновлюємо ПІБ через auth_manager для сумісності
                from auth import auth_manager
                auth_manager.update_user_full_name(user_id, full_name if full_name else None)
                
                # Оновлюємо права доступу
                user.can_edit_schedule = can_edit_schedule
                user.can_edit_academic = can_edit_academic
                session.commit()
                
                flash('ПІБ та права викладача оновлено!', 'success')
            else:
                flash('Користувача не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка оновлення: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Видалення користувача та всіх пов'язаних даних"""
    try:
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                # Забороняємо видалення адміністраторів
                if user.role == 'admin':
                    flash('Неможливо видалити адміністратора!', 'danger')
                    return redirect(url_for('users'))
                
                # Забороняємо видалення розробника
                developer_id = DEVELOPER_TELEGRAM_ID
                if developer_id and str(user_id) == str(developer_id):
                    flash('Неможливо видалити розробника системи!', 'danger')
                    return redirect(url_for('users'))
                
                username = user.username
                
                # Видаляємо пов'язані дані користувача
                # Деякі дані залишаємо для статистики та аудиту
                deleted_count = 0
                kept_for_stats = 0
                
                # 1. Видаляємо запити на доступ (не потрібні для статистики)
                pending_deleted = session.query(PendingRequest).filter(
                    PendingRequest.user_id == user_id
                ).delete()
                deleted_count += pending_deleted
                
                # 2. Видаляємо заняття викладача (поточні дані, не статистика)
                schedule_deleted = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == user_id
                ).delete()
                deleted_count += schedule_deleted
                
                # 3. Видаляємо академічні періоди викладача (поточні дані)
                periods_deleted = session.query(AcademicPeriod).filter(
                    AcademicPeriod.teacher_user_id == user_id
                ).delete()
                deleted_count += periods_deleted
                
                # 4. ЗАЛИШАЄМО записи отримувачів оголошень для статистики відправки
                # (скільки оголошень було відправлено, статистика доставки)
                announcement_recipients_count = session.query(AnnouncementRecipient).filter(
                    AnnouncementRecipient.recipient_user_id == user_id
                ).count()
                kept_for_stats += announcement_recipients_count
                
                # 5. Оновлюємо групи, де користувач був куратором (встановлюємо NULL)
                groups_updated = session.query(Group).filter(
                    Group.curator_user_id == user_id
                ).update({Group.curator_user_id: None})
                deleted_count += groups_updated
                
                # 6. ЗАЛИШАЄМО закриті опитування для статистики (активні видаляємо)
                # Видаляємо тільки активні опитування, створені користувачем
                active_polls_deleted = session.query(Poll).filter(
                    Poll.author_id == user_id,
                    Poll.is_closed == False
                ).delete()
                deleted_count += active_polls_deleted
                
                # Рахуємо закриті опитування, які залишаємо
                closed_polls_count = session.query(Poll).filter(
                    Poll.author_id == user_id,
                    Poll.is_closed == True
                ).count()
                kept_for_stats += closed_polls_count
                
                # 7. ЗАЛИШАЄМО відповіді користувача на опитування для статистики
                # (результати опитувань важливі для аналітики)
                poll_responses_count = session.query(PollResponse).filter(
                    PollResponse.user_id == user_id
                ).count()
                kept_for_stats += poll_responses_count
                
                # 8. ЗАЛИШАЄМО історію оповіщень для статистики
                # (скільки оповіщень було відправлено користувачу)
                notification_history_count = session.query(NotificationHistory).filter(
                    NotificationHistory.user_id == user_id
                ).count()
                kept_for_stats += notification_history_count
                
                # 9. Видаляємо налаштування оповіщень (не статистика)
                notification_settings_deleted = session.query(NotificationSettings).filter(
                    NotificationSettings.user_id == user_id
                ).delete()
                deleted_count += notification_settings_deleted
                
                # 10. ЗАЛИШАЄМО логи користувача для аудиту та статистики
                logs_count = session.query(Log).filter(Log.user_id == user_id).count()
                kept_for_stats += logs_count
                
                # 11. Видаляємо самого користувача
                session.delete(user)
                session.commit()
                
                # Логування критичної дії
                logger.log_warning(
                    f"КРИТИЧНА ДІЯ: Користувач {current_user.user_id} ({current_user.full_name}) "
                    f"видалив користувача {user_id} (@{username}). "
                    f"Видалено записів: {deleted_count}, залишено для статистики: {kept_for_stats}",
                    user_id=current_user.user_id
                )
                
                # Формуємо повідомлення з інформацією про збережені дані
                message = f'Користувача @{username} видалено!'
                if deleted_count > 0:
                    message += f' Видалено {deleted_count} записів.'
                if kept_for_stats > 0:
                    message += f' Збережено {kept_for_stats} записів для статистики та аудиту.'
                
                flash(message, 'success')
            else:
                flash('Користувача не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення користувача: {e}', 'danger')
        import traceback
        logger.log_error(f"Помилка видалення користувача: {traceback.format_exc()}")
    
    return redirect(url_for('users'))


def send_telegram_message(user_id: int, message: str) -> bool:
    """
    Відправка повідомлення користувачу через Telegram Bot API
    
    Args:
        user_id: ID користувача в Telegram
        message: Текст повідомлення
        
    Returns:
        True якщо повідомлення відправлено успішно, False інакше
    """
    if not TELEGRAM_API_URL:
        return False
    
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                'chat_id': user_id,
                'text': message,
                'parse_mode': 'HTML'
            },
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        logger.log_error(f"Помилка відправки повідомлення в Telegram: {e}")
        return False


@app.route('/users/approve/<int:user_id>', methods=['POST'])
@admin_required
def approve_request(user_id):
    """Схвалення запиту на доступ"""
    try:
        with get_session() as session:
            request_obj = session.query(PendingRequest).filter(PendingRequest.user_id == user_id).first()
            if not request_obj:
                flash('Запит не знайдено!', 'warning')
                return redirect(url_for('users'))
            
            username = request_obj.username
            
            # Створюємо користувача з роллю 'user' за замовчуванням
            user = User(
                user_id=request_obj.user_id,
                username=username,
                approved_at=datetime.now(),
                notifications_enabled=False,
                role='user'
            )
            session.add(user)
            session.delete(request_obj)
            session.commit()
            
            # Відправляємо повідомлення користувачу про схвалення
            approval_message = (
                "✅ <b>Ваш запит на доступ схвалено!</b>\n\n"
                "Тепер ви маєте доступ до розкладу занять.\n\n"
                "Використовуйте команду /start або /menu для початку роботи."
            )
            send_telegram_message(user_id, approval_message)
            
            flash(f'Запит від @{username} схвалено! Користувач отримав повідомлення.', 'success')
    except Exception as e:
        flash(f'Помилка схвалення запиту: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/deny/<int:user_id>', methods=['POST'])
@admin_required
def deny_request(user_id):
    """Відхилення запиту на доступ"""
    try:
        with get_session() as session:
            request_obj = session.query(PendingRequest).filter(PendingRequest.user_id == user_id).first()
            if request_obj:
                username = request_obj.username
                session.delete(request_obj)
                session.commit()
                
                # Відправляємо повідомлення користувачу про відхилення
                denial_message = (
                    "❌ <b>Ваш запит на доступ відхилено</b>\n\n"
                    "На жаль, ваш запит на доступ до розкладу занять було відхилено адміністратором.\n\n"
                    "Якщо ви вважаєте, що це помилка, зверніться до адміністратора."
                )
                send_telegram_message(user_id, denial_message)
                
                flash(f'Запит від @{username} відхилено! Користувач отримав повідомлення.', 'success')
            else:
                flash('Запит не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка відхилення запиту: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/toggle-notifications/<int:user_id>', methods=['POST'])
@admin_required
def toggle_notifications(user_id):
    """Перемикання оповіщень користувача"""
    try:
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.notifications_enabled = not user.notifications_enabled
                session.commit()
                
                status = 'увімкнені' if user.notifications_enabled else 'вимкнені'
                flash(f'Оповіщення для @{user.username} {status}!', 'success')
            else:
                flash('Користувача не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка зміни оповіщень: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/set-password/<int:user_id>', methods=['POST'])
@admin_required
def set_user_password(user_id):
    """Встановлення пароля для користувача"""
    try:
        password = request.form.get('password', '').strip()
        
        if not password:
            flash('Пароль не може бути порожнім.', 'warning')
            return redirect(url_for('users'))
        
        if len(password) < 6:
            flash('Пароль повинен містити мінімум 6 символів.', 'warning')
            return redirect(url_for('users'))
        
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.password_hash = generate_password_hash(password)
                session.commit()
                flash(f'Пароль для @{user.username} встановлено!', 'success')
            else:
                flash('Користувача не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка встановлення пароля: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/schedule')
@login_required
def schedule():
    """Управління розкладом"""
    try:
        with get_session() as session:
            # Для користувачів - тільки їх розклад
            if not current_user.is_admin:
                teacher_filter = current_user.user_id
            else:
                # Для адмінів - можна вибрати викладача
                teacher_filter = request.args.get('teacher_id', type=int)
            
            # Отримуємо викладачів для вибору (тільки для адмінів)
            if current_user.is_admin:
                teachers = session.query(User).all()
                existing_teacher_ids = {t.user_id for t in teachers}
                
                teachers_in_schedule = session.query(ScheduleEntry.teacher_user_id).distinct().all()
                teacher_ids_in_schedule = {t[0] for t in teachers_in_schedule if t[0] is not None}
                
                for teacher_id in teacher_ids_in_schedule:
                    if teacher_id not in existing_teacher_ids:
                        user = session.query(User).filter(User.user_id == teacher_id).first()
                        if user:
                            teachers.append(user)
            else:
                teachers = []
            
            # Отримуємо заняття з фільтрацією
            # Розклад показується тільки для конкретного викладача
            entries = []
            if teacher_filter:
                query = session.query(ScheduleEntry).filter(ScheduleEntry.teacher_user_id == teacher_filter)
                entries = query.order_by(ScheduleEntry.time).all()
            metadata = session.query(ScheduleMetadata).first()
            
            # Групуємо по днях та типу тижня
            schedule_data = {}
            days_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_names = {
                'monday': 'Понеділок', 'tuesday': 'Вівторок', 'wednesday': 'Середа',
                'thursday': 'Четвер', 'friday': "П'ятниця", 'saturday': 'Субота', 'sunday': 'Неділя'
            }
            
            for day in days_order:
                schedule_data[day] = {
                    'numerator': [],
                    'denominator': []
                }
            
            # Отримуємо список груп для вибору
            groups = session.query(Group).order_by(Group.name).all()
            
            # Створюємо словник викладачів для швидкого доступу
            teachers_dict = {t.user_id: t for t in teachers}
            
            # Створюємо словник груп для швидкого доступу
            groups_dict = {}
            if groups:
                groups_dict = {g.id: g for g in groups}
            
            for entry in entries:
                if entry.day_of_week in schedule_data:
                    # Додаємо інформацію про викладача до entry
                    if entry.teacher_user_id and entry.teacher_user_id in teachers_dict:
                        teacher = teachers_dict[entry.teacher_user_id]
                        entry.teacher_display = teacher.full_name if teacher.full_name else entry.teacher
                    else:
                        entry.teacher_display = entry.teacher
                    
                    # Додаємо інформацію про групу до entry
                    if entry.group_id and entry.group_id in groups_dict:
                        entry.group_name = groups_dict[entry.group_id].name
                    else:
                        entry.group_name = None
                    
                    schedule_data[entry.day_of_week][entry.week_type].append(entry)
            
            return render_template('schedule.html',
                                 schedule=schedule_data,
                                 metadata=metadata,
                                 days_order=days_order,
                                 day_names=day_names,
                                 teachers=teachers,
                                 groups=groups,
                                 selected_teacher_id=teacher_filter)
    except Exception as e:
        flash(f'Помилка завантаження розкладу: {e}', 'danger')
        return render_template('schedule.html', schedule={}, metadata=None, days_order=[], day_names={}, teachers=[], groups=[], selected_teacher_id=None)


@app.route('/schedule/add', methods=['POST'])
@login_required
def add_schedule_entry():
    """Додавання заняття"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_schedule:
            flash('У вас немає прав для додавання заняття!', 'danger')
            return redirect(url_for('schedule'))
        
        with get_session() as session:
            # Для користувачів (не адмінів) автоматично встановлюємо їх user_id
            if current_user.is_admin:
                teacher_user_id = request.form.get('teacher_user_id', type=int)
            else:
                teacher_user_id = current_user.user_id
            
            # Отримуємо ПІБ викладача, якщо вказано teacher_user_id
            teacher_name = request.form.get('teacher', '')
            if teacher_user_id:
                user = session.query(User).filter(User.user_id == teacher_user_id).first()
                if user and getattr(user, 'full_name', None):
                    teacher_name = user.full_name
            
            group_id = request.form.get('group_id', type=int)
            
            entry = ScheduleEntry(
                day_of_week=request.form['day_of_week'],
                time=request.form['time'],
                subject=request.form['subject'],
                lesson_type=request.form['lesson_type'],
                teacher=teacher_name,  # Зберігаємо для сумісності
                teacher_user_id=teacher_user_id,
                teacher_phone=request.form.get('teacher_phone', ''),
                classroom=request.form.get('classroom', ''),
                conference_link=request.form.get('conference_link', ''),
                exam_type=request.form.get('exam_type', 'залік'),
                week_type=request.form['week_type'],
                group_id=group_id if group_id else None
            )
            session.add(entry)
            session.commit()
            
            flash(f'Заняття "{entry.subject}" додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/schedule/edit/<int:entry_id>', methods=['POST'])
@login_required
def edit_schedule_entry(entry_id):
    """Редагування заняття"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_schedule:
            flash('У вас немає прав для редагування заняття!', 'danger')
            return redirect(url_for('schedule'))
        
        with get_session() as session:
            entry = session.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
            if entry:
                # Перевіряємо права доступу: користувач може редагувати тільки свої заняття
                if not current_user.is_admin and entry.teacher_user_id != current_user.user_id:
                    flash('У вас немає прав для редагування цього заняття!', 'danger')
                    return redirect(url_for('schedule'))
                
                # Для адмінів - беремо з форми, для користувачів - автоматично з поточного користувача
                if current_user.is_admin:
                    teacher_user_id = request.form.get('teacher_user_id', type=int)
                else:
                    teacher_user_id = current_user.user_id
                
                # Отримуємо ПІБ викладача, якщо вказано teacher_user_id
                teacher_name = request.form.get('teacher', '')
                if teacher_user_id:
                    user = session.query(User).filter(User.user_id == teacher_user_id).first()
                    if user and getattr(user, 'full_name', None):
                        teacher_name = user.full_name
                
                group_id = request.form.get('group_id', type=int)
                
                entry.day_of_week = request.form['day_of_week']
                entry.time = request.form['time']
                entry.subject = request.form['subject']
                entry.lesson_type = request.form['lesson_type']
                entry.teacher = teacher_name  # Зберігаємо для сумісності
                entry.teacher_user_id = teacher_user_id
                # Телефон викладача тільки для адмінів
                if current_user.is_admin:
                    entry.teacher_phone = request.form.get('teacher_phone', '')
                entry.classroom = request.form.get('classroom', '')
                entry.conference_link = request.form.get('conference_link', '')
                entry.exam_type = request.form.get('exam_type', 'залік')
                entry.week_type = request.form['week_type']
                entry.group_id = group_id if group_id else None
                session.commit()
                
                flash(f'Заняття "{entry.subject}" оновлено!', 'success')
            else:
                flash('Заняття не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/schedule/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_schedule_entry(entry_id):
    """Видалення заняття"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_schedule:
            flash('У вас немає прав для видалення заняття!', 'danger')
            return redirect(url_for('schedule'))
        
        with get_session() as session:
            entry = session.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
            if entry:
                # Перевіряємо права доступу: користувач може видаляти тільки свої заняття
                if not current_user.is_admin and entry.teacher_user_id != current_user.user_id:
                    flash('У вас немає прав для видалення цього заняття!', 'danger')
                    return redirect(url_for('schedule'))
                subject = entry.subject
                session.delete(entry)
                session.commit()
                flash(f'Заняття "{subject}" видалено!', 'success')
            else:
                flash('Заняття не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/schedule/copy', methods=['POST'])
@admin_required
def copy_schedule():
    """Копіювання розкладу від одного викладача до іншого"""
    try:
        from_teacher_id = request.form.get('from_teacher_id', type=int)
        to_teacher_id = request.form.get('to_teacher_id', type=int)
        replace_existing = request.form.get('replace_existing') == 'on'  # Чи замінювати існуючі записи
        
        if not from_teacher_id or not to_teacher_id:
            flash('Виберіть вихідного та цільового викладача!', 'warning')
            return redirect(url_for('schedule'))
        
        if from_teacher_id == to_teacher_id:
            flash('Вихідний та цільовий викладач не можуть бути однаковими!', 'warning')
            return redirect(url_for('schedule'))
        
        with get_session() as session:
            # Перевіряємо існування користувачів
            from_teacher = session.query(User).filter(User.user_id == from_teacher_id).first()
            to_teacher = session.query(User).filter(User.user_id == to_teacher_id).first()
            
            if not from_teacher or not to_teacher:
                flash('Одного з викладачів не знайдено!', 'danger')
                return redirect(url_for('schedule'))
            
            # Отримуємо ПІБ цільового викладача
            to_teacher_name = to_teacher.full_name if to_teacher.full_name else to_teacher.username or f"ID: {to_teacher_id}"
            
            # Отримуємо всі записи розкладу від вихідного викладача
            source_entries = session.query(ScheduleEntry).filter(
                ScheduleEntry.teacher_user_id == from_teacher_id
            ).all()
            
            if not source_entries:
                flash(f'У викладача {from_teacher.full_name or from_teacher.username} немає записів розкладу для копіювання!', 'warning')
                return redirect(url_for('schedule'))
            
            # Якщо replace_existing, видаляємо існуючі записи цільового викладача
            if replace_existing:
                existing_entries = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == to_teacher_id
                ).all()
                for entry in existing_entries:
                    session.delete(entry)
            
            # Копіюємо записи
            copied_count = 0
            for source_entry in source_entries:
                new_entry = ScheduleEntry(
                    day_of_week=source_entry.day_of_week,
                    time=source_entry.time,
                    subject=source_entry.subject,
                    lesson_type=source_entry.lesson_type,
                    teacher=to_teacher_name,  # Оновлюємо ПІБ викладача
                    teacher_user_id=to_teacher_id,
                    teacher_phone=source_entry.teacher_phone,
                    classroom=source_entry.classroom,
                    conference_link=source_entry.conference_link,
                    exam_type=source_entry.exam_type,
                    week_type=source_entry.week_type,
                    group_id=source_entry.group_id  # Група залишається та сама
                )
                session.add(new_entry)
                copied_count += 1
            
            session.commit()
            
            from_name = from_teacher.full_name or from_teacher.username or f"ID: {from_teacher_id}"
            to_name = to_teacher.full_name or to_teacher.username or f"ID: {to_teacher_id}"
            flash(f'Розклад скопійовано від {from_name} до {to_name}! Скопійовано записів: {copied_count}', 'success')
    except Exception as e:
        flash(f'Помилка копіювання розкладу: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/logs')
@admin_required
def logs():
    """Перегляд логів"""
    try:
        # Параметри фільтрації
        level = request.args.get('level', '')
        search = request.args.get('search', '')
        command = request.args.get('command', '')
        page = int(request.args.get('page', 1))
        per_page = 100
        
        with get_session() as session:
            query = session.query(Log).order_by(Log.timestamp.desc())
            
            # Фільтри
            if level:
                query = query.filter(Log.level == level)
            if search:
                query = query.filter(Log.message.contains(search))
            if command:
                query = query.filter(Log.command == command)
            
            # Отримуємо список доступних команд для фільтра
            from sqlalchemy import func, distinct
            available_commands = session.query(distinct(Log.command)).filter(
                Log.command.isnot(None)
            ).order_by(Log.command).all()
            available_commands = [cmd[0] for cmd in available_commands]
            
            # Пагінація
            total = query.count()
            logs_list = query.offset((page-1)*per_page).limit(per_page).all()
            
            total_pages = (total + per_page - 1) // per_page
            
            return render_template('logs.html',
                                 logs=logs_list,
                                 page=page,
                                 total_pages=total_pages,
                                 total=total,
                                 level=level,
                                 search=search,
                                 command=command,
                                 available_commands=available_commands)
    except Exception as e:
        flash(f'Помилка завантаження логів: {e}', 'danger')
        return render_template('logs.html', logs=[], page=1, total_pages=1, total=0, available_commands=[])


@app.route('/logs/clear', methods=['POST'])
@admin_required
def clear_old_logs():
    """Очищення логів"""
    try:
        action = request.form.get('action', 'old')  # 'old' або 'all'
        
        with get_session() as session:
            if action == 'all':
                # Видаляємо всі логи
                deleted = session.query(Log).count()
                session.query(Log).delete()
                session.commit()
                flash(f'Видалено всі логи ({deleted} записів)', 'success')
            else:
                # Видаляємо старі логи
                days = int(request.form.get('days', 30))
                cutoff_date = datetime.now() - timedelta(days=days)
                deleted = session.query(Log).filter(Log.timestamp < cutoff_date).delete()
                session.commit()
                flash(f'Видалено {deleted} записів логів старше {days} днів', 'success')
    except Exception as e:
        flash(f'Помилка очищення логів: {e}', 'danger')
    
    return redirect(url_for('logs'))


@app.route('/settings')
@admin_required
def settings():
    """Загальні налаштування"""
    try:
        with get_session() as session:
            metadata = session.query(ScheduleMetadata).first()
            configs = session.query(BotConfig).all()
            
            config_dict = {c.key: c.value for c in configs}
            
            # Обчислюємо поточний тип тижня (автоматично) та наступну дату перемикання
            current_week_type = None
            next_switch_date = None
            if metadata and metadata.numerator_start_date:
                from schedule_handler import get_schedule_handler
                schedule_handler = get_schedule_handler()
                if schedule_handler:
                    current_week_type = schedule_handler.get_current_week_type()
                    
                    # Обчислюємо наступну неділю (дата перемикання)
                    today = datetime.now().date()
                    days_since_sunday = today.weekday() + 1  # Днів з неділі (1-7)
                    if days_since_sunday == 7:
                        # Сьогодні неділя, наступна неділя через тиждень
                        next_switch_date = today + timedelta(days=7)
                    else:
                        # Наступна неділя
                        next_switch_date = today + timedelta(days=(7 - days_since_sunday))
            
            return render_template('settings.html',
                                 metadata=metadata,
                                 configs=config_dict,
                                 current_week_type=current_week_type,
                                 next_switch_date=next_switch_date)
    except Exception as e:
        flash(f'Помилка завантаження налаштувань: {e}', 'danger')
        return render_template('settings.html', metadata=None, configs={}, current_week_type=None, next_switch_date=None)


@app.route('/settings/update', methods=['POST'])
@admin_required
def update_settings():
    """Оновлення налаштувань"""
    try:
        with get_session() as session:
            metadata = session.query(ScheduleMetadata).first()
            if not metadata:
                metadata = ScheduleMetadata()
                session.add(metadata)
            
            # Оновлюємо поля
            week_changed = False
            if 'group_name' in request.form:
                metadata.group_name = request.form['group_name']
            if 'academic_year' in request.form:
                metadata.academic_year = request.form['academic_year']
            if 'current_week' in request.form:
                old_week = metadata.current_week
                new_week = request.form['current_week']
                # Встановлюємо дату відліку якщо змінився тип тижня або дата ще не встановлена
                if old_week != new_week or not metadata.numerator_start_date:
                    # Встановлюємо новий тип тижня
                    metadata.current_week = new_week
                    week_changed = True
                    
                    # Встановлюємо дату початку відліку для автоматичного перемикання
                    # Знаходимо поточну неділю (початок поточного тижня)
                    today = datetime.now().date()
                    # weekday(): 0 = понеділок, 6 = неділя
                    # Знаходимо найближчу минулу неділю (або сьогодні, якщо сьогодні неділя)
                    days_since_sunday = today.weekday() + 1  # Днів з неділі (1-7)
                    if days_since_sunday == 7:
                        # Сьогодні неділя
                        current_sunday = today
                    else:
                        # Знаходимо минулу неділю (початок поточного тижня)
                        current_sunday = today - timedelta(days=days_since_sunday)
                    
                    # Встановлюємо дату початку відліку = поточна неділя
                    # Якщо встановлено "Чисельник", то week_number = 0 (парне) = чисельник
                    # Якщо встановлено "Знаменник", то зміщуємо дату на тиждень назад,
                    # щоб поточна неділя мала week_number = 1 (непарне) = знаменник
                    if new_week == "denominator":
                        # Зміщуємо дату на тиждень назад, щоб поточна неділя була знаменником
                        reference_date = current_sunday - timedelta(days=7)
                    else:
                        # Для чисельника поточна неділя = дата початку відліку
                        reference_date = current_sunday
                    
                    # Встановлюємо дату початку відліку
                    metadata.numerator_start_date = reference_date.strftime("%Y-%m-%d")
                    
                    week_type_display = "чисельник" if new_week == "numerator" else "знаменник"
                    flash(f'Тип тижня встановлено на "{week_type_display}" для поточного тижня. Система автоматично перемикатиметься кожну неділю.', 'success')
            
            metadata.last_updated = datetime.now()
            session.commit()
            
            # Очищаємо кеш розкладу при зміні типу тижня
            if week_changed:
                try:
                    from schedule_handler import get_schedule_handler
                    schedule_handler = get_schedule_handler()
                    if schedule_handler:
                        schedule_handler._cache = {}  # Очищаємо кеш
                        schedule_handler._cache_time = None
                except Exception as e:
                    # Логуємо помилку, але не блокуємо збереження налаштувань
                    logger.log_error(f"Помилка очищення кешу: {e}")
            
            if not week_changed:
                flash('Налаштування оновлено!', 'success')
    except Exception as e:
        flash(f'Помилка оновлення налаштувань: {e}', 'danger')
    
    return redirect(url_for('settings'))


@app.route('/contact-developer', methods=['GET', 'POST'])
@login_required
def contact_developer():
    """Форма зв'язку з розробником"""
    developer_configured = bool(DEVELOPER_TELEGRAM_ID)
    
    if request.method == 'POST':
        try:
            subject = request.form.get('subject', '').strip()
            message = request.form.get('message', '').strip()
            
            if not subject or not message:
                flash('Заповніть всі поля!', 'warning')
                return render_template('contact_developer.html')
            
            if not DEVELOPER_TELEGRAM_ID:
                flash('ID розробника не налаштовано в конфігурації!', 'danger')
                return render_template('contact_developer.html')
            
            # Формуємо повідомлення для розробника
            admin_name = current_user.full_name or current_user.username or f"ID: {current_user.user_id}"
            telegram_message = (
                f"🔧 <b>Повідомлення від адміністратора</b>\n\n"
                f"👤 <b>Від:</b> {admin_name}\n"
                f"🆔 <b>User ID:</b> {current_user.user_id}\n"
                f"📋 <b>Тема:</b> {subject}\n\n"
                f"💬 <b>Повідомлення:</b>\n{message}"
            )
            
            # Відправляємо повідомлення розробнику
            developer_id = int(DEVELOPER_TELEGRAM_ID)
            if send_telegram_message(developer_id, telegram_message):
                flash('Повідомлення успішно відправлено розробнику!', 'success')
            else:
                flash('Помилка відправки повідомлення. Перевірте налаштування бота.', 'danger')
            
            return redirect(url_for('contact_developer'))
        except Exception as e:
            flash(f'Помилка відправки повідомлення: {e}', 'danger')
            return render_template('contact_developer.html', developer_configured=developer_configured)
    
    return render_template('contact_developer.html', developer_configured=developer_configured)


@app.route('/announcements')
@admin_required
def announcements():
    """Управління оголошеннями"""
    try:
        from announcement_manager import get_announcement_manager
        announcement_manager = get_announcement_manager()
        
        # Отримуємо історію оголошень та список викладачів в одній сесії
        with get_session() as session:
            # Отримуємо історію оголошень
            announcements_list = session.query(Announcement).order_by(
                Announcement.sent_at.desc()
            ).limit(100).all()
            
            announcement_history = []
            for ann in announcements_list:
                announcement_history.append({
                    'id': ann.id,
                    'content': ann.content[:100] + '...' if len(ann.content) > 100 else ann.content,
                    'author_username': ann.author_username,
                    'priority': ann.priority,
                    'sent_at': ann.sent_at if ann.sent_at else None,
                    'recipient_count': ann.recipient_count or 0,
                    'created_at': ann.created_at
                })
            
            # Отримуємо список викладачів для вибору
            teachers_list = session.query(User).all()
            teachers = []
            for teacher in teachers_list:
                teachers.append({
                    'user_id': teacher.user_id,
                    'username': teacher.username or f"user_{teacher.user_id}",
                    'full_name': getattr(teacher, 'full_name', None)
                })
        
        return render_template('announcements.html',
                             announcements=announcement_history,
                             teachers=teachers)
    except Exception as e:
        flash(f'Помилка завантаження оголошень: {e}', 'danger')
        return render_template('announcements.html', announcements=[], teachers=[])


@app.route('/announcements/create', methods=['POST'])
@admin_required
def create_announcement():
    """Створення та відправка оголошення"""
    try:
        from announcement_manager import get_announcement_manager
        announcement_manager = get_announcement_manager()
        
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal')
        author_id = int(request.form.get('author_id', 0))
        author_username = request.form.get('author_username', 'admin')
        
        # Отримуємо список отримувачів
        send_to_all = request.form.get('send_to_all') == 'on'
        
        if send_to_all:
            # Отримуємо всіх викладачів
            teachers = announcement_manager.get_all_teachers()
            recipient_ids = [t['user_id'] for t in teachers]
        else:
            # Отримуємо вибраних викладачів
            recipient_ids = [int(rid) for rid in request.form.getlist('recipient_ids')]
        
        if not recipient_ids:
            flash('Виберіть хоча б одного отримувача!', 'warning')
            return redirect(url_for('announcements'))
        
        if not content:
            flash('Введіть текст оголошення!', 'warning')
            return redirect(url_for('announcements'))
        
        # Відправляємо оголошення
        result = announcement_manager.send_announcement_to_users(
            recipient_user_ids=recipient_ids,
            content=content,
            priority=priority,
            author_id=author_id,
            author_username=author_username
        )
        
        if result['sent'] > 0:
            flash(f'Оголошення відправлено {result["sent"]} викладачам!', 'success')
        if result['failed'] > 0:
            flash(f'Помилка відправки {result["failed"]} оголошень', 'warning')
            
    except Exception as e:
        flash(f'Помилка створення оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/announcements/edit/<int:ann_id>', methods=['POST'])
@admin_required
def edit_announcement(ann_id):
    """Редагування оголошення"""
    try:
        with get_session() as session:
            announcement = session.query(Announcement).filter(Announcement.id == ann_id).first()
            if announcement:
                announcement.content = request.form['content']
                announcement.priority = request.form.get('priority', 'normal')
                announcement.updated_at = datetime.now()
                session.commit()
                
                flash('Оголошення оновлено!', 'success')
            else:
                flash('Оголошення не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/announcements/delete/<int:ann_id>', methods=['POST'])
@admin_required
def delete_announcement(ann_id):
    """Видалення оголошення"""
    try:
        from announcement_manager import get_announcement_manager
        announcement_manager = get_announcement_manager()
        
        if announcement_manager.delete_announcement(ann_id):
            flash('Оголошення видалено!', 'success')
        else:
            flash('Оголошення не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/announcements/<int:ann_id>/recipients')
@admin_required
def announcement_recipients(ann_id):
    """Перегляд отримувачів оголошення"""
    try:
        from announcement_manager import get_announcement_manager
        announcement_manager = get_announcement_manager()
        
        # Отримуємо оголошення та отримувачів в одній сесії
        with get_session() as session:
            announcement_obj = session.query(Announcement).filter(Announcement.id == ann_id).first()
            if not announcement_obj:
                flash('Оголошення не знайдено!', 'warning')
                return redirect(url_for('announcements'))
            
            # Конвертуємо оголошення в словник
            announcement = {
                'id': announcement_obj.id,
                'content': announcement_obj.content,
                'author_username': announcement_obj.author_username,
                'priority': announcement_obj.priority,
                'sent_at': announcement_obj.sent_at,
                'recipient_count': announcement_obj.recipient_count or 0,
                'created_at': announcement_obj.created_at
            }
            
            # Отримуємо отримувачів
            recipients_list = session.query(AnnouncementRecipient, User).join(
                User, AnnouncementRecipient.recipient_user_id == User.user_id
            ).filter(
                AnnouncementRecipient.announcement_id == ann_id
            ).all()
            
            recipients = []
            for recipient, user in recipients_list:
                recipients.append({
                    'recipient_user_id': recipient.recipient_user_id,
                    'username': user.username or f"user_{user.user_id}",
                    'full_name': getattr(user, 'full_name', None),
                    'sent_at': recipient.sent_at,
                    'status': recipient.status
                })
        
        return render_template('announcement_recipients.html',
                             announcement=announcement,
                             recipients=recipients)
    except Exception as e:
        flash(f'Помилка завантаження отримувачів: {e}', 'danger')
        return redirect(url_for('announcements'))


@app.route('/polls')
@admin_required
def polls():
    """Управління опитуваннями"""
    try:
        poll_manager = get_poll_manager()
        active_polls = poll_manager.get_active_polls()
        
        # Отримуємо закриті опитування
        with get_session() as session:
            closed_polls = session.query(Poll).filter(
                Poll.is_closed == True
            ).order_by(Poll.closed_at.desc()).limit(50).all()
            
            closed_polls_data = []
            for poll in closed_polls:
                author = session.query(User).filter(User.user_id == poll.author_id).first()
                author_name = author.full_name if author and author.full_name else poll.author_username or f"ID: {poll.author_id}"
                
                response_count = session.query(PollResponse).filter(
                    PollResponse.poll_id == poll.id
                ).count()
                
                closed_polls_data.append({
                    'id': poll.id,
                    'question': poll.question,
                    'author_name': author_name,
                    'created_at': poll.created_at,
                    'closed_at': poll.closed_at,
                    'response_count': response_count,
                    'report_sent': poll.report_sent,
                    'is_anonymous': poll.is_anonymous
                })
        
        # Отримуємо список всіх користувачів для вибору отримувачів
        all_users = session.query(User).filter(User.role == 'user').order_by(User.full_name, User.username).all()
        
        return render_template('polls.html', active_polls=active_polls, closed_polls=closed_polls_data, all_users=all_users)
    except Exception as e:
        flash(f'Помилка завантаження опитувань: {e}', 'danger')
        return render_template('polls.html', active_polls=[], closed_polls=[])


@app.route('/polls/create', methods=['POST'])
@admin_required
def create_poll():
    """Створення нового опитування"""
    try:
        question = request.form.get('question', '').strip()
        options_text = request.form.get('options', '').strip()
        expires_at_str = request.form.get('expires_at', '').strip()
        is_anonymous = request.form.get('is_anonymous') == '1'
        
        if not question:
            flash('Питання опитування не може бути порожнім!', 'warning')
            return redirect(url_for('polls'))
        
        # Парсимо варіанти відповіді (кожен з нового рядка)
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        
        if len(options) < 2:
            flash('Потрібно мінімум 2 варіанти відповіді!', 'warning')
            return redirect(url_for('polls'))
        
        if len(options) > 10:
            flash('Максимум 10 варіантів відповіді!', 'warning')
            return redirect(url_for('polls'))
        
        # Парсимо термін дії
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    flash('Невірний формат дати терміну дії!', 'warning')
                    return redirect(url_for('polls'))
        
        poll_manager = get_poll_manager()
        # Автор завжди адмін (з веб-інтерфейсу)
        author_name = current_user.full_name or current_user._username or "Адміністратор"
        poll_id = poll_manager.create_poll(
            question=question,
            options=options,
            author_id=current_user.user_id,
            author_username=author_name,
            expires_at=expires_at,
            is_anonymous=is_anonymous
        )
        
        if poll_id:
            flash(f'Опитування створено! ID: {poll_id}', 'success')
        else:
            flash('Помилка створення опитування!', 'danger')
    except Exception as e:
        flash(f'Помилка створення опитування: {e}', 'danger')
    
    return redirect(url_for('polls'))


@app.route('/polls/<int:poll_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_poll(poll_id):
    """Редагування опитування (тільки якщо воно ще не відправлено)"""
    try:
        with get_session() as session:
            poll = session.query(Poll).filter(Poll.id == poll_id).first()
            if not poll:
                flash('Опитування не знайдено!', 'warning')
                return redirect(url_for('polls'))
            
            # Перевіряємо чи опитування вже відправлено
            if poll.sent_to_users:
                flash('Неможливо редагувати опитування, яке вже відправлено користувачам!', 'warning')
                return redirect(url_for('polls'))
            
            # Перевіряємо чи опитування не закрите
            if poll.is_closed:
                flash('Неможливо редагувати закрите опитування!', 'warning')
                return redirect(url_for('polls'))
            
            if request.method == 'POST':
                question = request.form.get('question', '').strip()
                options_text = request.form.get('options', '').strip()
                expires_at_str = request.form.get('expires_at', '').strip()
                is_anonymous = request.form.get('is_anonymous') == '1'
                
                if not question:
                    flash('Питання опитування не може бути порожнім!', 'warning')
                    return redirect(url_for('edit_poll', poll_id=poll_id))
                
                # Парсимо варіанти відповіді (кожен з нового рядка)
                options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
                
                if len(options) < 2:
                    flash('Потрібно мінімум 2 варіанти відповіді!', 'warning')
                    return redirect(url_for('edit_poll', poll_id=poll_id))
                
                if len(options) > 10:
                    flash('Максимум 10 варіантів відповіді!', 'warning')
                    return redirect(url_for('edit_poll', poll_id=poll_id))
                
                # Парсимо термін дії
                expires_at = None
                if expires_at_str:
                    try:
                        expires_at = datetime.strptime(expires_at_str, '%Y-%m-%dT%H:%M')
                    except ValueError:
                        try:
                            expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M')
                        except ValueError:
                            flash('Невірний формат дати терміну дії!', 'warning')
                            return redirect(url_for('edit_poll', poll_id=poll_id))
                
                poll_manager = get_poll_manager()
                if poll_manager.update_poll(
                    poll_id=poll_id,
                    question=question,
                    options=options,
                    expires_at=expires_at,
                    is_anonymous=is_anonymous
                ):
                    flash(f'Опитування ID {poll_id} успішно оновлено!', 'success')
                else:
                    flash('Помилка оновлення опитування!', 'danger')
                
                return redirect(url_for('polls'))
            else:
                # GET - показуємо форму редагування
                # Отримуємо варіанти відповіді
                options = session.query(PollOption).filter(
                    PollOption.poll_id == poll_id
                ).order_by(PollOption.option_order).all()
                
                options_text = '\n'.join([opt.option_text for opt in options])
                
                # Форматуємо дату для input datetime-local
                expires_at_str = ''
                if poll.expires_at:
                    expires_at_str = poll.expires_at.strftime('%Y-%m-%dT%H:%M')
                
                return render_template('edit_poll.html', 
                                     poll=poll, 
                                     options_text=options_text,
                                     expires_at_str=expires_at_str)
    except Exception as e:
        flash(f'Помилка редагування опитування: {e}', 'danger')
        return redirect(url_for('polls'))


@app.route('/polls/<int:poll_id>/results')
@admin_required
def poll_results(poll_id):
    """Результати опитування"""
    try:
        poll_manager = get_poll_manager()
        results = poll_manager.get_poll_results(poll_id)
        
        if not results:
            flash('Опитування не знайдено!', 'warning')
            return redirect(url_for('polls'))
        
        # Отримуємо інформацію про опитування (для перевірки is_anonymous)
        with get_session() as session:
            poll = session.query(Poll).filter(Poll.id == poll_id).first()
            is_anonymous = poll.is_anonymous if poll else False
            
            # Отримуємо відповіді користувачів (тільки для неанонімних опитувань)
            user_responses = []
            if not is_anonymous:
                responses = session.query(PollResponse, User, PollOption).join(
                    User, PollResponse.user_id == User.user_id
                ).join(
                    PollOption, PollResponse.option_id == PollOption.id
                ).filter(
                    PollResponse.poll_id == poll_id
                ).order_by(PollResponse.responded_at.desc()).all()
                
                for response, user, option in responses:
                    user_responses.append({
                        'user_id': user.user_id,
                        'username': user.username or f"user_{user.user_id}",
                        'full_name': user.full_name,
                        'option_text': option.option_text,
                        'response_time': response.responded_at
                    })
        
        results['is_anonymous'] = is_anonymous
        results['user_responses'] = user_responses
        
        return render_template('poll_results.html', results=results)
    except Exception as e:
        flash(f'Помилка завантаження результатів: {e}', 'danger')
        return redirect(url_for('polls'))


@app.route('/polls/<int:poll_id>/send', methods=['POST'])
@admin_required
def send_poll(poll_id):
    """Відправка опитування користувачам з кнопками для голосування"""
    try:
        send_to_all = request.form.get('send_to_all') == '1'
        recipient_ids = request.form.getlist('recipient_ids')
        
        # Валідація
        if not send_to_all and not recipient_ids:
            flash('Оберіть отримувачів або встановіть "Відправити всім"!', 'warning')
            return redirect(url_for('polls'))
        
        poll_manager = get_poll_manager()
        
        # Визначаємо список отримувачів
        user_ids = None if send_to_all else [int(uid) for uid in recipient_ids]
        
        # Відправляємо опитування
        send_stats = poll_manager.send_poll_to_users(poll_id, user_ids=user_ids)
        
        if send_to_all:
            flash(
                f'Опитування відправлено всім користувачам ({send_stats["sent"]} успішно). '
                f'Помилок: {send_stats["failed"]}',
                'success'
            )
        else:
            flash(
                f'Опитування відправлено {send_stats["sent"]} обраним користувачам. '
                f'Помилок: {send_stats["failed"]}',
                'success'
            )
    except Exception as e:
        flash(f'Помилка відправки опитування: {e}', 'danger')
    
    return redirect(url_for('polls'))


@app.route('/polls/<int:poll_id>/close', methods=['POST'])
@admin_required
def close_poll(poll_id):
    """Закриття опитування та опціональна відправка звіту"""
    try:
        send_report = request.form.get('send_report') == '1'
        poll_manager = get_poll_manager()
        
        # Закриваємо опитування
        if not poll_manager.close_poll(poll_id):
            flash('Помилка закриття опитування!', 'danger')
            return redirect(url_for('polls'))
        
        # Відправляємо звіт тільки якщо встановлено
        if send_report:
            report_stats = poll_manager.send_poll_report_to_users(poll_id)
            flash(
                f'Опитування закрито! Звіт відправлено {report_stats["sent"]} користувачам. '
                f'Помилок: {report_stats["failed"]}',
                'success'
            )
        else:
            flash('Опитування закрито без відправки звіту.', 'success')
    except Exception as e:
        flash(f'Помилка закриття опитування: {e}', 'danger')
    
    return redirect(url_for('polls'))


@app.route('/polls/<int:poll_id>/delete', methods=['POST'])
@admin_required
def delete_poll(poll_id):
    """Видалення закритого опитування з бази даних"""
    try:
        with get_session() as session:
            poll = session.query(Poll).filter(Poll.id == poll_id).first()
            
            if not poll:
                flash('Опитування не знайдено!', 'warning')
                return redirect(url_for('polls'))
            
            # Перевіряємо, що опитування закрите
            if not poll.is_closed:
                flash('Можна видаляти тільки закриті опитування!', 'warning')
                return redirect(url_for('polls'))
            
            # Отримуємо кількість відповідей для інформації
            response_count = session.query(PollResponse).filter(
                PollResponse.poll_id == poll_id
            ).count()
            
            # Видаляємо опитування (CASCADE автоматично видалить PollOption та PollResponse)
            session.delete(poll)
            session.commit()
            
            flash(
                f'Опитування "{poll.question[:50]}..." успішно видалено! '
                f'Видалено {response_count} відповідей користувачів.',
                'success'
            )
    except Exception as e:
        flash(f'Помилка видалення опитування: {e}', 'danger')
    
    return redirect(url_for('polls'))


@app.route('/academic')
@login_required
def academic():
    """Академічний календар"""
    try:
        with get_session() as session:
            # Для користувачів - тільки їх періоди
            if not current_user.is_admin:
                teacher_filter = current_user.user_id
            else:
                # Для адмінів - можна вибрати викладача
                teacher_filter = request.args.get('teacher_id', type=int)
            
            # Отримуємо викладачів для вибору
            if current_user.is_admin:
                # Для адмінів - всі викладачі
                teachers = session.query(User).all()
                existing_teacher_ids = {t.user_id for t in teachers}
                
                # Також додаємо викладачів, які є в періодах (teacher_user_id), але можуть не бути в списку користувачів
                teachers_in_periods = session.query(AcademicPeriod.teacher_user_id).distinct().all()
                teacher_ids_in_periods = {t[0] for t in teachers_in_periods if t[0] is not None}
                
                # Додаємо викладачів з періодів, яких немає в списку
                for teacher_id in teacher_ids_in_periods:
                    if teacher_id not in existing_teacher_ids:
                        user = session.query(User).filter(User.user_id == teacher_id).first()
                        if user:
                            teachers.append(user)
            else:
                # Для звичайних користувачів - тільки поточний користувач
                teachers = [current_user]
                existing_teacher_ids = {current_user.user_id}
            
            # Отримуємо періоди з фільтрацією
            # Показуємо тільки періоди з встановленим teacher_user_id (не загальні)
            query = session.query(AcademicPeriod).filter(AcademicPeriod.teacher_user_id.isnot(None))
            if teacher_filter:
                query = query.filter(AcademicPeriod.teacher_user_id == teacher_filter)
            periods = query.order_by(AcademicPeriod.start_date).all()
            
            metadata = session.query(ScheduleMetadata).first()
            
            # Створюємо словник викладачів для відображення
            teachers_dict = {t.user_id: t for t in teachers}
            
            # Додаємо інформацію про викладача до періодів
            for period in periods:
                if period.teacher_user_id and period.teacher_user_id in teachers_dict:
                    teacher = teachers_dict[period.teacher_user_id]
                    period.teacher_display = teacher.full_name if teacher.full_name else (teacher.username or f"ID: {teacher.user_id}")
                else:
                    period.teacher_display = f"ID: {period.teacher_user_id}" if period.teacher_user_id else "Загальний"
            
            return render_template('academic.html',
                                 periods=periods,
                                 metadata=metadata,
                                 teachers=teachers,
                                 selected_teacher_id=teacher_filter)
    except Exception as e:
        flash(f'Помилка завантаження календаря: {e}', 'danger')
        return render_template('academic.html', periods=[], metadata=None, teachers=[], selected_teacher_id=None)


@app.route('/academic/add', methods=['POST'])
@login_required
def add_academic_period():
    """Додавання академічного періоду"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_academic:
            flash('У вас немає прав для додавання академічного періоду!', 'danger')
            return redirect(url_for('academic'))
        
        with get_session() as session:
            # Для користувачів (не адмінів) автоматично встановлюємо їх user_id
            if current_user.is_admin:
                teacher_user_id = request.form.get('teacher_user_id', type=int)
                # Перевіряємо, що викладач обов'язково вказаний для адмінів
                if not teacher_user_id:
                    flash('Помилка: необхідно вибрати викладача для періоду!', 'danger')
                    return redirect(url_for('academic'))
            else:
                teacher_user_id = current_user.user_id
            
            period = AcademicPeriod(
                period_id=request.form['period_id'],
                name=request.form['name'],
                start_date=request.form['start_date'],
                end_date=request.form['end_date'],
                weeks=int(request.form['weeks']),
                color=request.form.get('color', '🟦'),
                description=request.form.get('description', ''),
                teacher_user_id=teacher_user_id
            )
            session.add(period)
            session.commit()
            
            flash(f'Період "{period.name}" додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання періоду: {e}', 'danger')
    
    # Перенаправляємо з фільтром
    teacher_id = request.form.get('teacher_user_id', type=int)
    if teacher_id:
        return redirect(url_for('academic', teacher_id=teacher_id))
    return redirect(url_for('academic'))


@app.route('/academic/edit/<int:period_id>', methods=['POST'])
@login_required
def edit_academic_period(period_id):
    """Редагування періоду"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_academic:
            flash('У вас немає прав для редагування академічного періоду!', 'danger')
            return redirect(url_for('academic'))
        
        with get_session() as session:
            period = session.query(AcademicPeriod).filter(AcademicPeriod.id == period_id).first()
            if period:
                # Перевіряємо права доступу: користувач може редагувати тільки свої періоди
                if not current_user.is_admin and period.teacher_user_id != current_user.user_id:
                    flash('У вас немає прав для редагування цього періоду!', 'danger')
                    return redirect(url_for('academic'))
                
                # Для користувачів (не адмінів) автоматично встановлюємо їх user_id
                if current_user.is_admin:
                    teacher_user_id = request.form.get('teacher_user_id', type=int)
                    # Перевіряємо, що викладач обов'язково вказаний для адмінів
                    if not teacher_user_id:
                        flash('Помилка: необхідно вибрати викладача для періоду!', 'danger')
                        # Перенаправляємо з фільтром поточного періоду
                        if period.teacher_user_id:
                            return redirect(url_for('academic', teacher_id=period.teacher_user_id))
                        return redirect(url_for('academic'))
                else:
                    teacher_user_id = current_user.user_id
                
                period.name = request.form['name']
                period.start_date = request.form['start_date']
                period.end_date = request.form['end_date']
                period.weeks = int(request.form['weeks'])
                period.color = request.form.get('color', '🟦')
                period.description = request.form.get('description', '')
                period.teacher_user_id = teacher_user_id
                session.commit()
                
                flash(f'Період "{period.name}" оновлено!', 'success')
            else:
                flash('Період не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування періоду: {e}', 'danger')
    
    # Перенаправляємо з фільтром
    teacher_id = request.form.get('teacher_user_id', type=int)
    if teacher_id:
        return redirect(url_for('academic', teacher_id=teacher_id))
    return redirect(url_for('academic'))


@app.route('/academic/delete/<int:period_id>', methods=['POST'])
@login_required
def delete_academic_period(period_id):
    """Видалення періоду"""
    try:
        # Перевірка прав для звичайних користувачів
        if not current_user.is_admin and not current_user.can_edit_academic:
            flash('У вас немає прав для видалення академічного періоду!', 'danger')
            return redirect(url_for('academic'))
        
        with get_session() as session:
            period = session.query(AcademicPeriod).filter(AcademicPeriod.id == period_id).first()
            if period:
                # Перевіряємо права доступу: користувач може видаляти тільки свої періоди
                if not current_user.is_admin and period.teacher_user_id != current_user.user_id:
                    flash('У вас немає прав для видалення цього періоду!', 'danger')
                    return redirect(url_for('academic'))
                teacher_id = period.teacher_user_id
                name = period.name
                session.delete(period)
                session.commit()
                flash(f'Період "{name}" видалено!', 'success')
                
                # Перенаправляємо з фільтром, якщо він був встановлений
                if teacher_id:
                    return redirect(url_for('academic', teacher_id=teacher_id))
            else:
                flash('Період не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення періоду: {e}', 'danger')
    
    return redirect(url_for('academic'))


@app.route('/academic/copy', methods=['POST'])
@admin_required
def copy_academic_calendar():
    """Копіювання академічного календаря від одного викладача до іншого"""
    try:
        from_teacher_id = request.form.get('from_teacher_id', type=int)
        to_teacher_id = request.form.get('to_teacher_id', type=int)
        replace_existing = request.form.get('replace_existing') == 'on'  # Чи замінювати існуючі записи
        
        if not from_teacher_id or not to_teacher_id:
            flash('Виберіть вихідного та цільового викладача!', 'warning')
            return redirect(url_for('academic'))
        
        if from_teacher_id == to_teacher_id:
            flash('Вихідний та цільовий викладач не можуть бути однаковими!', 'warning')
            return redirect(url_for('academic'))
        
        with get_session() as session:
            # Перевіряємо існування користувачів
            from_teacher = session.query(User).filter(User.user_id == from_teacher_id).first()
            to_teacher = session.query(User).filter(User.user_id == to_teacher_id).first()
            
            if not from_teacher or not to_teacher:
                flash('Одного з викладачів не знайдено!', 'danger')
                return redirect(url_for('academic'))
            
            # Отримуємо всі періоди від вихідного викладача
            source_periods = session.query(AcademicPeriod).filter(
                AcademicPeriod.teacher_user_id == from_teacher_id
            ).all()
            
            if not source_periods:
                flash(f'У викладача {from_teacher.full_name or from_teacher.username} немає періодів для копіювання!', 'warning')
                return redirect(url_for('academic'))
            
            # Якщо replace_existing, видаляємо існуючі періоди цільового викладача
            if replace_existing:
                existing_periods = session.query(AcademicPeriod).filter(
                    AcademicPeriod.teacher_user_id == to_teacher_id
                ).all()
                for period in existing_periods:
                    session.delete(period)
            
            # Копіюємо періоди
            copied_count = 0
            for source_period in source_periods:
                # Генеруємо унікальний period_id для нового періоду
                new_period_id = f"{to_teacher_id}_{uuid.uuid4().hex[:8]}"
                
                new_period = AcademicPeriod(
                    period_id=new_period_id,
                    name=source_period.name,
                    start_date=source_period.start_date,
                    end_date=source_period.end_date,
                    weeks=source_period.weeks,
                    color=source_period.color,
                    description=source_period.description,
                    teacher_user_id=to_teacher_id
                )
                session.add(new_period)
                copied_count += 1
            
            session.commit()
            
            from_name = from_teacher.full_name or from_teacher.username or f"ID: {from_teacher_id}"
            to_name = to_teacher.full_name or to_teacher.username or f"ID: {to_teacher_id}"
            flash(f'Академічний календар скопійовано від {from_name} до {to_name}! Скопійовано періодів: {copied_count}', 'success')
    except Exception as e:
        flash(f'Помилка копіювання академічного календаря: {e}', 'danger')
    
    return redirect(url_for('academic'))


def calculate_teacher_workload(session, teacher_user_id: int) -> Dict[str, Any]:
    """
    Розрахунок навантаження годин для викладача за тиждень
    
    Args:
        session: SQLAlchemy session
        teacher_user_id: ID викладача
        
    Returns:
        Словник з навантаженням: total_hours, by_day, by_type, lessons_count
    """
    try:
        # Отримуємо всі заняття викладача
        entries = session.query(ScheduleEntry).filter(
            ScheduleEntry.teacher_user_id == teacher_user_id
        ).all()
        
        # Розраховуємо години
        total_hours = 0
        by_day = {}
        by_type = {}
        lessons_count = 0
        
        for entry in entries:
            # Парсимо час (наприклад, "08:30-09:50")
            try:
                time_str = entry.time
                if '-' in time_str:
                    start_str, end_str = time_str.split('-')
                    start = datetime.strptime(start_str, "%H:%M")
                    end = datetime.strptime(end_str, "%H:%M")
                    duration = (end - start).total_seconds() / 3600  # Години
                    total_hours += duration
                    lessons_count += 1
                    
                    # По днях
                    day = entry.day_of_week
                    by_day[day] = by_day.get(day, 0) + duration
                    
                    # По типах заняття
                    lesson_type = entry.lesson_type
                    by_type[lesson_type] = by_type.get(lesson_type, 0) + duration
            except (ValueError, AttributeError):
                continue
        
        return {
            'total_hours': round(total_hours, 2),
            'by_day': by_day,
            'by_type': by_type,
            'lessons_count': lessons_count
        }
    except Exception as e:
        return {'total_hours': 0, 'by_day': {}, 'by_type': {}, 'lessons_count': 0}


def calculate_teacher_workload_by_week_type(session, teacher_user_id: int, week_type: str) -> Dict[str, Any]:
    """
    Розрахунок навантаження годин для викладача за конкретний тип тижня
    
    Args:
        session: SQLAlchemy session
        teacher_user_id: ID викладача
        week_type: Тип тижня ('numerator', 'denominator')
        
    Returns:
        Словник з навантаженням: total_hours, lessons_count
    """
    try:
        # Отримуємо заняття викладача для конкретного типу тижня
        entries = session.query(ScheduleEntry).filter(
            ScheduleEntry.teacher_user_id == teacher_user_id,
            ScheduleEntry.week_type == week_type
        ).all()
        
        total_hours = 0
        lessons_count = 0
        
        for entry in entries:
            try:
                time_str = entry.time
                if '-' in time_str:
                    start_str, end_str = time_str.split('-')
                    start = datetime.strptime(start_str, "%H:%M")
                    end = datetime.strptime(end_str, "%H:%M")
                    duration = (end - start).total_seconds() / 3600
                    total_hours += duration
                    lessons_count += 1
            except (ValueError, AttributeError):
                continue
        
        return {
            'total_hours': round(total_hours, 2),
            'lessons_count': lessons_count
        }
    except Exception as e:
        return {'total_hours': 0, 'lessons_count': 0}


@app.route('/stats')
@admin_required
def stats():
    """Статистика використання"""
    try:
        with get_session() as session:
            from sqlalchemy import func
            
            # Статистика по командах
            command_stats = session.query(
                Log.command,
                func.count(Log.id).label('count')
            ).filter(
                Log.command.isnot(None)
            ).group_by(Log.command).order_by(func.count(Log.id).desc()).limit(10).all()
            
            # Активність по днях (останні 30 днів)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            daily_activity = session.query(
                func.date(Log.timestamp).label('date'),
                func.count(Log.id).label('count')
            ).filter(
                Log.timestamp >= thirty_days_ago
            ).group_by(func.date(Log.timestamp)).order_by(func.date(Log.timestamp)).all()
            
            # Топ активних користувачів
            top_users = session.query(
                Log.user_id,
                func.count(Log.id).label('activity_count')
            ).filter(
                Log.user_id.isnot(None),
                Log.timestamp >= thirty_days_ago
            ).group_by(Log.user_id).order_by(func.count(Log.id).desc()).limit(10).all()
            
            # Отримуємо дані користувачів
            user_activity = []
            for user_id, count in top_users:
                user = session.query(User).filter(User.user_id == user_id).first()
                user_activity.append({
                    'user_id': user_id,
                    'username': user.username if user else 'невідомий',
                    'count': count
                })
            
            # Навантаження викладачів
            teachers = session.query(User).filter(User.role == 'user').all()
            teacher_workload = []
            for teacher in teachers:
                workload = calculate_teacher_workload(session, teacher.user_id)
                teacher_workload.append({
                    'user_id': teacher.user_id,
                    'username': teacher.username,
                    'full_name': teacher.full_name,
                    'total_hours': workload['total_hours'],
                    'lessons_count': workload['lessons_count']
                })
            
            # Сортуємо по навантаженню
            teacher_workload.sort(key=lambda x: x['total_hours'], reverse=True)
            
            # Загальна статистика
            total_logs = session.query(Log).count()
            total_errors = session.query(Log).filter(Log.level == 'ERROR').count()
            total_warnings = session.query(Log).filter(Log.level == 'WARNING').count()
            total_security = session.query(Log).filter(Log.level == 'SECURITY').count()
            
            general_stats = {
                'total_logs': total_logs,
                'total_errors': total_errors,
                'total_warnings': total_warnings,
                'total_security': total_security,
                'total_info': total_logs - total_errors - total_warnings - total_security
            }
            
            return render_template('stats.html',
                                 command_stats=command_stats,
                                 daily_activity=daily_activity,
                                 user_activity=user_activity,
                                 general_stats=general_stats,
                                 teacher_workload=teacher_workload)
    except Exception as e:
        flash(f'Помилка завантаження статистики: {e}', 'danger')
        return render_template('stats.html', command_stats=[], daily_activity=[], user_activity=[], general_stats={}, teacher_workload=[])


@app.route('/admin/schedule-report')
@admin_required
def schedule_report():
    """Монітор навчального процесу - дашборд з заняттями користувачів"""
    try:
        with get_session() as session:
            # Отримуємо всіх користувачів (викладачів) - без фільтрів, показуємо всіх
            teachers = session.query(User).filter(User.role == 'user').order_by(User.full_name, User.username).all()
            
            # Отримуємо всі групи (для відображення назв груп)
            groups = session.query(Group).order_by(Group.name).all()
            
            # Мапінг днів тижня
            day_names = {
                'monday': 'Понеділок',
                'tuesday': 'Вівторок',
                'wednesday': 'Середа',
                'thursday': 'Четвер',
                'friday': 'П\'ятниця',
                'saturday': 'Субота',
                'sunday': 'Неділя'
            }
            days_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            
            # Визначаємо поточний день та час для фільтрації "зараз"
            weekday_map = {
                0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                4: 'friday', 5: 'saturday', 6: 'sunday'
            }
            current_day = weekday_map[datetime.now().weekday()]
            current_time = datetime.now().time()
            
            # Визначаємо поточний тип тижня
            from schedule_handler import get_schedule_handler
            schedule_handler = get_schedule_handler()
            if schedule_handler:
                current_week_type = schedule_handler.get_current_week_type()
            else:
                metadata_for_week = session.query(ScheduleMetadata).first()
                if metadata_for_week and metadata_for_week.current_week in ["numerator", "denominator"]:
                    current_week_type = metadata_for_week.current_week
                else:
                    current_week_type = 'numerator'
            
            # Для кожного користувача завантажуємо його заняття
            users_data = []
            for teacher in teachers:
                # Запит для заняття користувача
                entries_query = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id == teacher.user_id
                )
                
                # Фільтр: тільки поточний день та поточний тип тижня
                entries_query = entries_query.filter(
                    ScheduleEntry.day_of_week == current_day,
                    ScheduleEntry.week_type == current_week_type
                )
                
                entries = entries_query.order_by(ScheduleEntry.time).all()
                
                # Фільтруємо заняття по поточному часу (тільки ті, що зараз проходять)
                current_entries = []
                for entry in entries:
                    try:
                        # Парсимо час заняття (формат "HH:MM-HH:MM")
                        if '-' in entry.time:
                            start_str, end_str = entry.time.split('-')
                            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                            
                            # Перевіряємо, чи поточний час знаходиться між початком та кінцем
                            if start_time <= current_time <= end_time:
                                current_entries.append(entry)
                    except (ValueError, AttributeError):
                        # Якщо не вдалося розпарсити час, пропускаємо
                        continue
                
                entries = current_entries
                
                # Додаємо інформацію про групи до entries та парсимо час для прогресу
                groups_dict = {g.id: g for g in groups}
                for entry in entries:
                    if entry.group_id and entry.group_id in groups_dict:
                        entry.group_name = groups_dict[entry.group_id].name
                    else:
                        entry.group_name = None
                    
                    # Парсимо час для розрахунку прогресу
                    if '-' in entry.time:
                        try:
                            start_str, end_str = entry.time.split('-')
                            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                            
                            # Зберігаємо час початку та кінця як рядки для JavaScript
                            entry.start_time_str = start_str.strip()
                            entry.end_time_str = end_str.strip()
                            
                            # Розраховуємо тривалість в хвилинах
                            start_datetime = datetime.combine(datetime.today(), start_time)
                            end_datetime = datetime.combine(datetime.today(), end_time)
                            if end_datetime < start_datetime:
                                end_datetime += timedelta(days=1)
                            duration_minutes = (end_datetime - start_datetime).total_seconds() / 60
                            entry.duration_minutes = int(duration_minutes)
                        except (ValueError, AttributeError):
                            entry.start_time_str = None
                            entry.end_time_str = None
                            entry.duration_minutes = None
                    else:
                        entry.start_time_str = None
                        entry.end_time_str = None
                        entry.duration_minutes = None
                
                # Групуємо заняття по днях та типу тижня (для поточного дня)
                schedule_data = {}
                for day in days_order:
                    schedule_data[day] = {
                        'numerator': [],
                        'denominator': []
                    }
                
                # Додаємо заняття тільки для поточного дня
                for entry in entries:
                    if entry.day_of_week in schedule_data:
                        schedule_data[entry.day_of_week][entry.week_type].append(entry)
                
                users_data.append({
                    'teacher': teacher,
                    'schedule': schedule_data,
                    'entries_count': len(entries)
                })
            
            # Метадані для відображення
            metadata = session.query(ScheduleMetadata).first()
            
            return render_template('schedule_report.html',
                                 users_data=users_data,
                                 teachers=teachers,
                                 groups=groups,
                                 day_names=day_names,
                                 days_order=days_order,
                                 metadata=metadata,
                                 current_day=current_day,
                                 current_week_type=current_week_type)
    except Exception as e:
        logger.log_error(f"Помилка завантаження звіту по розкладу: {e}")
        flash(f'Помилка завантаження звіту: {e}', 'danger')
        return render_template('schedule_report.html',
                             users_data=[],
                             teachers=[],
                             groups=[],
                             day_names={},
                             days_order=[],
                             metadata=None,
                             current_day=None,
                             current_week_type=None)


# Favicon handler (ігноруємо запити на favicon.ico)
@app.route('/favicon.ico')
def favicon():
    """Обробка запитів на favicon.ico"""
    return '', 204  # No Content


# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Обробка 404 помилок"""
    # Не логуємо 404 для favicon.ico
    if '/favicon.ico' not in request.url:
        if FLASK_ENV == 'production':
            logger.log_warning(f"404 помилка: {request.url}")
    return render_template('error.html', error_code=404, error_message='Сторінку не знайдено'), 404


@app.errorhandler(500)
def internal_error(error):
    """Обробка 500 помилок"""
    logger.log_error(f"500 помилка: {str(error)}")
    if FLASK_ENV == 'production':
        return render_template('error.html', error_code=500, error_message='Внутрішня помилка сервера'), 500
    else:
        # В development показуємо деталі помилки
        raise error


@app.errorhandler(429)
def ratelimit_handler(e):
    """Обробка rate limit помилок"""
    logger.log_warning(f"Rate limit exceeded для IP {get_remote_address()}")
    return jsonify({'error': 'Занадто багато запитів. Спробуйте пізніше.'}), 429


@app.route('/api/alert-status')
@csrf.exempt
@limiter.limit("30 per minute")
def api_alert_status():
    """API для отримання статусу повітряної тривоги з rate limiting"""
    try:
        import asyncio
        air_alert_manager = get_air_alert_manager()
        
        # Створюємо новий event loop для async виклику
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        alert_status = loop.run_until_complete(air_alert_manager.get_alert_status())
        loop.close()
        
        if alert_status and air_alert_manager.active_alerts:
            alert_types = set(alert.get('alert_type', 'unknown') for alert in air_alert_manager.active_alerts)
            
            if 'air_raid' in alert_types:
                message = f"ТРИВОГА в {air_alert_manager.city}!"
            elif 'artillery_shelling' in alert_types:
                message = f"ОБСТРІЛ в {air_alert_manager.city}!"
            else:
                message = f"ТРИВОГА в {air_alert_manager.city}!"
            
            return jsonify({
                'alert': True,
                'message': message,
                'city': air_alert_manager.city,
                'types': list(alert_types)
            })
        else:
            return jsonify({
                'alert': False,
                'message': f"ТИХО в {air_alert_manager.city}",
                'city': air_alert_manager.city
            })
    except Exception as e:
        return jsonify({
            'alert': False,
            'message': 'Статус недоступний',
            'error': str(e)
        })


@app.route('/groups')
@login_required
def groups():
    """Управління групами"""
    try:
        with get_session() as session:
            all_groups = session.query(Group).all()
            teachers = session.query(User).filter(User.role == 'user').all()
            
            # Додаємо інформацію про кураторів
            groups_data = []
            for group in all_groups:
                curator = None
                if group.curator_user_id:
                    curator = session.query(User).filter(User.user_id == group.curator_user_id).first()
                
                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'headman_name': group.headman_name,
                    'headman_phone': group.headman_phone,
                    'curator_user_id': group.curator_user_id,
                    'curator_display': curator.full_name if curator and curator.full_name else (curator.username if curator else 'Не встановлено'),
                    'created_at': group.created_at,
                    'updated_at': group.updated_at
                })
            
            return render_template('groups.html',
                                 groups=groups_data,
                                 teachers=teachers)
    except Exception as e:
        flash(f'Помилка завантаження груп: {e}', 'danger')
        return render_template('groups.html', groups=[], teachers=[])


@app.route('/groups/add', methods=['POST'])
@login_required
def add_group():
    """Додавання групи"""
    try:
        name = request.form.get('name', '').strip()
        headman_name = request.form.get('headman_name', '').strip()
        headman_phone = request.form.get('headman_phone', '').strip()
        curator_user_id = request.form.get('curator_user_id', type=int)
        
        if not name:
            flash('Назва групи обов\'язкова!', 'danger')
            return redirect(url_for('groups'))
        
        with get_session() as session:
            # Перевіряємо чи вже існує група з такою назвою
            existing = session.query(Group).filter(Group.name == name).first()
            if existing:
                flash(f'Група "{name}" вже існує!', 'warning')
                return redirect(url_for('groups'))
            
            group = Group(
                name=name,
                headman_name=headman_name if headman_name else None,
                headman_phone=headman_phone if headman_phone else None,
                curator_user_id=curator_user_id if curator_user_id else None
            )
            session.add(group)
            session.commit()
            
            flash(f'Групу "{name}" додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання групи: {e}', 'danger')
    
    return redirect(url_for('groups'))


@app.route('/groups/edit/<int:group_id>', methods=['POST'])
@login_required
def edit_group(group_id):
    """Редагування групи"""
    try:
        name = request.form.get('name', '').strip()
        headman_name = request.form.get('headman_name', '').strip()
        headman_phone = request.form.get('headman_phone', '').strip()
        curator_user_id = request.form.get('curator_user_id', type=int)
        
        if not name:
            flash('Назва групи обов\'язкова!', 'danger')
            return redirect(url_for('groups'))
        
        with get_session() as session:
            group = session.query(Group).filter(Group.id == group_id).first()
            if group:
                # Перевіряємо чи не існує інша група з такою назвою
                existing = session.query(Group).filter(Group.name == name, Group.id != group_id).first()
                if existing:
                    flash(f'Група "{name}" вже існує!', 'warning')
                    return redirect(url_for('groups'))
                
                group.name = name
                group.headman_name = headman_name if headman_name else None
                group.headman_phone = headman_phone if headman_phone else None
                group.curator_user_id = curator_user_id if curator_user_id else None
                group.updated_at = datetime.now()
                session.commit()
                
                flash(f'Групу "{name}" оновлено!', 'success')
            else:
                flash('Групу не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування групи: {e}', 'danger')
    
    return redirect(url_for('groups'))


@app.route('/groups/delete/<int:group_id>', methods=['POST'])
@login_required
def delete_group(group_id):
    """Видалення групи"""
    try:
        with get_session() as session:
            group = session.query(Group).filter(Group.id == group_id).first()
            if group:
                name = group.name
                session.delete(group)
                session.commit()
                flash(f'Групу "{name}" видалено!', 'success')
            else:
                flash('Групу не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення групи: {e}', 'danger')
    
    return redirect(url_for('groups'))


# PWA маршрути
@app.route('/manifest.json')
def manifest():
    """PWA Web App Manifest"""
    return send_file('static/manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
@csrf.exempt
def service_worker():
    """Service Worker для PWA"""
    response = send_file('static/js/sw.js', mimetype='application/javascript')
    # Дозволяємо service worker працювати на всіх сторінках
    response.headers['Service-Worker-Allowed'] = '/'
    # Відключаємо кешування для service worker (важливо для оновлень)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# Запуск додатку
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)

