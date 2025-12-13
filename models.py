"""
SQLAlchemy моделі для TeachHub
Містить всі таблиці БД для зберігання даних бота
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Модель користувача з доступом до бота"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    approved_at = Column(DateTime, default=datetime.now)
    notifications_enabled = Column(Boolean, default=False)
    role = Column(String(20), default='user')  # admin, user
    full_name = Column(String(200))  # ПІБ викладача (призначається адміном)
    password_hash = Column(String(255), nullable=True)  # Хеш пароля для веб-доступу
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, username='{self.username}', role='{self.role}', full_name='{self.full_name}')>"


class PendingRequest(Base):
    """Модель запитів на доступ"""
    __tablename__ = 'pending_requests'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    timestamp = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<PendingRequest(user_id={self.user_id}, username='{self.username}')>"


class ScheduleEntry(Base):
    """Модель заняття в розкладі"""
    __tablename__ = 'schedule_entries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    day_of_week = Column(String(20), nullable=False, index=True)  # monday, tuesday, etc.
    time = Column(String(20), nullable=False)  # 09:00-10:30
    subject = Column(String(200), nullable=False)
    lesson_type = Column(String(50), nullable=False)  # лекція, практика, лабораторна
    teacher = Column(String(200))  # Залишаємо для сумісності, але використовуємо teacher_user_id
    teacher_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True, index=True)  # ID викладача
    teacher_phone = Column(String(50))
    classroom = Column(String(50))
    conference_link = Column(String(500))
    exam_type = Column(String(50))  # залік, екзамен
    week_type = Column(String(20), nullable=False, index=True)  # numerator, denominator
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True, index=True)  # ID групи
    
    def __repr__(self):
        return f"<ScheduleEntry(day={self.day_of_week}, subject='{self.subject}', week={self.week_type}, teacher_user_id={self.teacher_user_id})>"


class ScheduleMetadata(Base):
    """Метадані розкладу (поточний тиждень, назва навчального закладу, рік)"""
    __tablename__ = 'schedule_metadata'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    current_week = Column(String(20), default='numerator')  # numerator або denominator
    group_name = Column(String(100), default='KCM-24-11')
    academic_year = Column(String(20), default='2025/2026')
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    numerator_start_date = Column(String(20))  # YYYY-MM-DD для автовизначення тижня
    
    def __repr__(self):
        return f"<ScheduleMetadata(group='{self.group_name}', week='{self.current_week}')>"


class AcademicPeriod(Base):
    """Модель періоду навчального року"""
    __tablename__ = 'academic_periods'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    period_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    start_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    end_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    weeks = Column(Integer, nullable=False)
    color = Column(String(10), default='🟦')  # emoji для візуалізації
    description = Column(Text)
    teacher_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True, index=True)  # ID викладача
    
    def __repr__(self):
        return f"<AcademicPeriod(name='{self.name}', start='{self.start_date}', teacher_user_id={self.teacher_user_id})>"


class Announcement(Base):
    """Модель оголошення"""
    __tablename__ = 'announcements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    author_id = Column(Integer, nullable=False)
    author_username = Column(String(100))
    priority = Column(String(20), default='normal')  # normal, important, urgent
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    sent_at = Column(DateTime)  # Час відправки оголошення
    recipient_count = Column(Integer, default=0)  # Кількість отримувачів
    
    def __repr__(self):
        return f"<Announcement(id={self.id}, priority='{self.priority}', sent_at='{self.sent_at}', recipients={self.recipient_count})>"


class AnnouncementRecipient(Base):
    """Модель отримувача оголошення (історія відправки)"""
    __tablename__ = 'announcement_recipients'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    announcement_id = Column(Integer, ForeignKey('announcements.id'), nullable=False, index=True)
    recipient_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    sent_at = Column(DateTime, default=datetime.now, index=True)
    status = Column(String(20), default='sent')  # sent, failed, blocked
    
    def __repr__(self):
        return f"<AnnouncementRecipient(announcement_id={self.announcement_id}, recipient_user_id={self.recipient_user_id}, status='{self.status}')>"


class NotificationHistory(Base):
    """Історія відправлених оповіщень"""
    __tablename__ = 'notification_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    lesson_key = Column(String(500), nullable=False)  # унікальний ключ заняття
    sent_at = Column(DateTime, default=datetime.now, index=True)
    notification_date = Column(String(20), index=True)  # YYYY-MM-DD для швидкої фільтрації
    
    def __repr__(self):
        return f"<NotificationHistory(user_id={self.user_id}, sent_at='{self.sent_at}')>"


class NotificationSettings(Base):
    """Налаштування оповіщень"""
    __tablename__ = 'notification_settings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=False)
    minutes_before = Column(Integer, default=10)  # за скільки хвилин нагадувати
    
    def __repr__(self):
        return f"<NotificationSettings(user_id={self.user_id}, enabled={self.enabled})>"


class Log(Base):
    """Системні логи"""
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    level = Column(String(20), nullable=False, index=True)  # INFO, WARNING, ERROR, SECURITY
    message = Column(Text, nullable=False)
    user_id = Column(Integer, index=True)
    command = Column(String(100))
    
    def __repr__(self):
        return f"<Log(level='{self.level}', timestamp='{self.timestamp}')>"


class BotConfig(Base):
    """Конфігурація бота (key-value пари)"""
    __tablename__ = 'bot_config'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text)
    description = Column(String(500))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<BotConfig(key='{self.key}', value='{self.value[:50]}')>"


class Group(Base):
    """Модель навчальної групи"""
    __tablename__ = 'groups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, index=True)  # Назва групи
    headman_name = Column(String(200))  # ПІБ старости групи
    headman_phone = Column(String(50))  # Телефон старости
    curator_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=True, index=True)  # ID куратора (викладача)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<Group(name='{self.name}', curator_user_id={self.curator_user_id})>"



