"""
Flask веб-інтерфейс для управління Schedule Bot
Адмін панель для управління користувачами, розкладом, оголошеннями тощо
"""
import os
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import CSRFProtect

# Додаємо батьківську директорію в Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import init_database, get_session
from models import (
    User, PendingRequest, ScheduleEntry, ScheduleMetadata,
    AcademicPeriod, Announcement, NotificationHistory,
    NotificationSettings, Log, BotConfig
)

# Ініціалізація Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['WTF_CSRF_ENABLED'] = True

# CSRF захист
csrf = CSRFProtect(app)

# Ініціалізація БД при запуску
init_database()


@app.route('/')
def dashboard():
    """Головна сторінка - Dashboard"""
    try:
        with get_session() as session:
            # Статистика
            stats = {
                'users_count': session.query(User).count(),
                'pending_requests': session.query(PendingRequest).count(),
                'schedule_entries': session.query(ScheduleEntry).count(),
                'announcements_count': session.query(Announcement).filter(Announcement.is_active == True).count(),
            }
            
            # Метадані розкладу
            metadata = session.query(ScheduleMetadata).first()
            
            # Останні логи
            recent_logs = session.query(Log).order_by(Log.timestamp.desc()).limit(10).all()
            
            return render_template('dashboard.html',
                                 stats=stats,
                                 metadata=metadata,
                                 logs=recent_logs)
    except Exception as e:
        flash(f'Помилка завантаження даних: {e}', 'danger')
        return render_template('dashboard.html', stats={}, metadata=None, logs=[])


@app.route('/users')
def users():
    """Управління користувачами"""
    try:
        with get_session() as session:
            all_users = session.query(User).all()
            pending = session.query(PendingRequest).all()
            
            return render_template('users.html',
                                 users=all_users,
                                 pending_requests=pending)
    except Exception as e:
        flash(f'Помилка завантаження користувачів: {e}', 'danger')
        return render_template('users.html', users=[], pending_requests=[])


@app.route('/users/add', methods=['POST'])
def add_user():
    """Додавання користувача"""
    try:
        user_id = int(request.form.get('user_id'))
        username = request.form.get('username', 'без username')
        
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
                notifications_enabled=False
            )
            session.add(user)
            session.commit()
            
            flash(f'Користувача @{username} додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання користувача: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Видалення користувача"""
    try:
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                username = user.username
                session.delete(user)
                session.commit()
                flash(f'Користувача @{username} видалено!', 'success')
            else:
                flash('Користувача не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення користувача: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/approve/<int:user_id>', methods=['POST'])
def approve_request(user_id):
    """Схвалення запиту на доступ"""
    try:
        with get_session() as session:
            request_obj = session.query(PendingRequest).filter(PendingRequest.user_id == user_id).first()
            if not request_obj:
                flash('Запит не знайдено!', 'warning')
                return redirect(url_for('users'))
            
            # Створюємо користувача
            user = User(
                user_id=request_obj.user_id,
                username=request_obj.username,
                approved_at=datetime.now(),
                notifications_enabled=False
            )
            session.add(user)
            session.delete(request_obj)
            session.commit()
            
            flash(f'Запит від @{request_obj.username} схвалено!', 'success')
    except Exception as e:
        flash(f'Помилка схвалення запиту: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/users/deny/<int:user_id>', methods=['POST'])
def deny_request(user_id):
    """Відхилення запиту на доступ"""
    try:
        with get_session() as session:
            request_obj = session.query(PendingRequest).filter(PendingRequest.user_id == user_id).first()
            if request_obj:
                username = request_obj.username
                session.delete(request_obj)
                session.commit()
                flash(f'Запит від @{username} відхилено!', 'success')
            else:
                flash('Запит не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка відхилення запиту: {e}', 'danger')
    
    return redirect(url_for('users'))


@app.route('/schedule')
def schedule():
    """Управління розкладом"""
    try:
        with get_session() as session:
            entries = session.query(ScheduleEntry).order_by(ScheduleEntry.time).all()
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
            
            for entry in entries:
                if entry.day_of_week in schedule_data:
                    schedule_data[entry.day_of_week][entry.week_type].append(entry)
            
            return render_template('schedule.html',
                                 schedule=schedule_data,
                                 metadata=metadata,
                                 days_order=days_order,
                                 day_names=day_names)
    except Exception as e:
        flash(f'Помилка завантаження розкладу: {e}', 'danger')
        return render_template('schedule.html', schedule={}, metadata=None, days_order=[], day_names={})


@app.route('/schedule/add', methods=['POST'])
def add_schedule_entry():
    """Додавання заняття"""
    try:
        with get_session() as session:
            entry = ScheduleEntry(
                day_of_week=request.form['day_of_week'],
                time=request.form['time'],
                subject=request.form['subject'],
                lesson_type=request.form['lesson_type'],
                teacher=request.form['teacher'],
                teacher_phone=request.form.get('teacher_phone', ''),
                classroom=request.form.get('classroom', ''),
                conference_link=request.form.get('conference_link', ''),
                exam_type=request.form.get('exam_type', 'залік'),
                week_type=request.form['week_type']
            )
            session.add(entry)
            session.commit()
            
            flash(f'Заняття "{entry.subject}" додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/schedule/edit/<int:entry_id>', methods=['POST'])
def edit_schedule_entry(entry_id):
    """Редагування заняття"""
    try:
        with get_session() as session:
            entry = session.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
            if entry:
                entry.day_of_week = request.form['day_of_week']
                entry.time = request.form['time']
                entry.subject = request.form['subject']
                entry.lesson_type = request.form['lesson_type']
                entry.teacher = request.form['teacher']
                entry.teacher_phone = request.form.get('teacher_phone', '')
                entry.classroom = request.form.get('classroom', '')
                entry.conference_link = request.form.get('conference_link', '')
                entry.exam_type = request.form.get('exam_type', 'залік')
                entry.week_type = request.form['week_type']
                session.commit()
                
                flash(f'Заняття "{entry.subject}" оновлено!', 'success')
            else:
                flash('Заняття не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/schedule/delete/<int:entry_id>', methods=['POST'])
def delete_schedule_entry(entry_id):
    """Видалення заняття"""
    try:
        with get_session() as session:
            entry = session.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
            if entry:
                subject = entry.subject
                session.delete(entry)
                session.commit()
                flash(f'Заняття "{subject}" видалено!', 'success')
            else:
                flash('Заняття не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення заняття: {e}', 'danger')
    
    return redirect(url_for('schedule'))


@app.route('/logs')
def logs():
    """Перегляд логів"""
    try:
        # Параметри фільтрації
        level = request.args.get('level', '')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 100
        
        with get_session() as session:
            query = session.query(Log).order_by(Log.timestamp.desc())
            
            # Фільтри
            if level:
                query = query.filter(Log.level == level)
            if search:
                query = query.filter(Log.message.contains(search))
            
            # Пагінація
            total = query.count()
            logs_list = query.offset((page-1)*per_page).limit(per_page).all()
            
            total_pages = (total + per_page - 1) // per_page
            
            return render_template('logs.html',
                                 logs=logs_list,
                                 page=page,
                                 total_pages=total_pages,
                                 level=level,
                                 search=search)
    except Exception as e:
        flash(f'Помилка завантаження логів: {e}', 'danger')
        return render_template('logs.html', logs=[], page=1, total_pages=1)


@app.route('/settings')
def settings():
    """Загальні налаштування"""
    try:
        with get_session() as session:
            metadata = session.query(ScheduleMetadata).first()
            configs = session.query(BotConfig).all()
            
            config_dict = {c.key: c.value for c in configs}
            
            return render_template('settings.html',
                                 metadata=metadata,
                                 configs=config_dict)
    except Exception as e:
        flash(f'Помилка завантаження налаштувань: {e}', 'danger')
        return render_template('settings.html', metadata=None, configs={})


@app.route('/settings/update', methods=['POST'])
def update_settings():
    """Оновлення налаштувань"""
    try:
        with get_session() as session:
            metadata = session.query(ScheduleMetadata).first()
            if not metadata:
                metadata = ScheduleMetadata()
                session.add(metadata)
            
            # Оновлюємо поля
            if 'group_name' in request.form:
                metadata.group_name = request.form['group_name']
            if 'academic_year' in request.form:
                metadata.academic_year = request.form['academic_year']
            if 'current_week' in request.form:
                metadata.current_week = request.form['current_week']
            
            metadata.last_updated = datetime.now()
            session.commit()
            
            flash('Налаштування оновлено!', 'success')
    except Exception as e:
        flash(f'Помилка оновлення налаштувань: {e}', 'danger')
    
    return redirect(url_for('settings'))


@app.route('/announcements')
def announcements():
    """Управління оголошеннями"""
    try:
        with get_session() as session:
            all_announcements = session.query(Announcement).order_by(Announcement.created_at.desc()).all()
            active_announcement = session.query(Announcement).filter(Announcement.is_active == True).first()
            
            return render_template('announcements.html',
                                 announcements=all_announcements,
                                 active_announcement=active_announcement)
    except Exception as e:
        flash(f'Помилка завантаження оголошень: {e}', 'danger')
        return render_template('announcements.html', announcements=[], active_announcement=None)


@app.route('/announcements/create', methods=['POST'])
def create_announcement():
    """Створення оголошення"""
    try:
        with get_session() as session:
            # Деактивуємо всі попередні
            session.query(Announcement).update({'is_active': False})
            
            announcement = Announcement(
                content=request.form['content'],
                author_id=int(request.form.get('author_id', 0)),
                author_username=request.form.get('author_username', 'admin'),
                priority=request.form.get('priority', 'normal'),
                created_at=datetime.now(),
                updated_at=datetime.now(),
                is_active=True
            )
            session.add(announcement)
            session.commit()
            
            flash('Оголошення створено!', 'success')
    except Exception as e:
        flash(f'Помилка створення оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/announcements/edit/<int:ann_id>', methods=['POST'])
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
def delete_announcement(ann_id):
    """Видалення оголошення"""
    try:
        with get_session() as session:
            announcement = session.query(Announcement).filter(Announcement.id == ann_id).first()
            if announcement:
                session.delete(announcement)
                session.commit()
                flash('Оголошення видалено!', 'success')
            else:
                flash('Оголошення не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/announcements/activate/<int:ann_id>', methods=['POST'])
def activate_announcement(ann_id):
    """Активація оголошення"""
    try:
        with get_session() as session:
            # Деактивуємо всі
            session.query(Announcement).update({'is_active': False})
            
            # Активуємо вибране
            announcement = session.query(Announcement).filter(Announcement.id == ann_id).first()
            if announcement:
                announcement.is_active = True
                session.commit()
                flash('Оголошення активовано!', 'success')
            else:
                flash('Оголошення не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка активації оголошення: {e}', 'danger')
    
    return redirect(url_for('announcements'))


@app.route('/academic')
def academic():
    """Академічний календар"""
    try:
        with get_session() as session:
            periods = session.query(AcademicPeriod).all()
            metadata = session.query(ScheduleMetadata).first()
            
            return render_template('academic.html',
                                 periods=periods,
                                 metadata=metadata)
    except Exception as e:
        flash(f'Помилка завантаження календаря: {e}', 'danger')
        return render_template('academic.html', periods=[], metadata=None)


@app.route('/academic/add', methods=['POST'])
def add_academic_period():
    """Додавання академічного періоду"""
    try:
        with get_session() as session:
            period = AcademicPeriod(
                period_id=request.form['period_id'],
                name=request.form['name'],
                start_date=request.form['start_date'],
                end_date=request.form['end_date'],
                weeks=int(request.form['weeks']),
                color=request.form.get('color', '🟦'),
                description=request.form.get('description', '')
            )
            session.add(period)
            session.commit()
            
            flash(f'Період "{period.name}" додано!', 'success')
    except Exception as e:
        flash(f'Помилка додавання періоду: {e}', 'danger')
    
    return redirect(url_for('academic'))


@app.route('/academic/edit/<int:period_id>', methods=['POST'])
def edit_academic_period(period_id):
    """Редагування періоду"""
    try:
        with get_session() as session:
            period = session.query(AcademicPeriod).filter(AcademicPeriod.id == period_id).first()
            if period:
                period.name = request.form['name']
                period.start_date = request.form['start_date']
                period.end_date = request.form['end_date']
                period.weeks = int(request.form['weeks'])
                period.color = request.form.get('color', '🟦')
                period.description = request.form.get('description', '')
                session.commit()
                
                flash(f'Період "{period.name}" оновлено!', 'success')
            else:
                flash('Період не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка редагування періоду: {e}', 'danger')
    
    return redirect(url_for('academic'))


@app.route('/academic/delete/<int:period_id>', methods=['POST'])
def delete_academic_period(period_id):
    """Видалення періоду"""
    try:
        with get_session() as session:
            period = session.query(AcademicPeriod).filter(AcademicPeriod.id == period_id).first()
            if period:
                name = period.name
                session.delete(period)
                session.commit()
                flash(f'Період "{name}" видалено!', 'success')
            else:
                flash('Період не знайдено!', 'warning')
    except Exception as e:
        flash(f'Помилка видалення періоду: {e}', 'danger')
    
    return redirect(url_for('academic'))


@app.route('/stats')
def stats():
    """Статистика використання"""
    try:
        with get_session() as session:
            # Статистика по командах
            from sqlalchemy import func
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
            ).group_by(func.date(Log.timestamp)).all()
            
            return render_template('stats.html',
                                 command_stats=command_stats,
                                 daily_activity=daily_activity)
    except Exception as e:
        flash(f'Помилка завантаження статистики: {e}', 'danger')
        return render_template('stats.html', command_stats=[], daily_activity=[])


# Запуск додатку
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)

