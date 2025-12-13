"""
Модуль управління базою даних для TeachHub
Надає функції для роботи з SQLite через SQLAlchemy
Підтримка конкурентного доступу (веб + Telegram бот)
"""
import os
import time
from contextlib import contextmanager
from typing import Optional, Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, DatabaseError
from dotenv import load_dotenv

from models import Base
from logger import logger

# Завантажуємо змінні середовища
load_dotenv("config.env")


class DatabaseManager:
    """Менеджер для роботи з базою даних"""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Ініціалізація менеджера БД
        
        Args:
            database_url: URL бази даних (за замовчуванням з config.env)
        """
        if database_url is None:
            database_url = os.getenv("DATABASE_URL", "sqlite:///schedule_bot.db")
        
        self.database_url = database_url
        
        # Створюємо engine з підтримкою конкурентного доступу
        if database_url.startswith("sqlite"):
            # Налаштування для одночасного доступу веб + бот
            self.engine = create_engine(
                database_url,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,  # Збільшений timeout до 30 секунд
                },
                pool_size=10,  # Розмір пулу з'єднань
                max_overflow=20,  # Максимум додаткових з'єднань
                pool_pre_ping=True,  # Перевірка з'єднання перед використанням
                pool_recycle=3600,  # Перестворення з'єднань кожну годину
                echo=False  # Встановіть True для debug SQL запитів
            )
            
            # Налаштування SQLite для конкурентного доступу
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                # Увімкнення foreign keys
                cursor.execute("PRAGMA foreign_keys=ON")
                # WAL mode для одночасного читання/запису
                cursor.execute("PRAGMA journal_mode=WAL")
                # Збільшення cache для продуктивності
                cursor.execute("PRAGMA cache_size=10000")
                # Синхронізація NORMAL (баланс безпека/швидкість)
                cursor.execute("PRAGMA synchronous=NORMAL")
                # Busy timeout 30 секунд
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
        else:
            self.engine = create_engine(database_url, echo=False)
        
        # Створюємо session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.log_info(f"Ініціалізовано підключення до БД: {database_url}")
    
    def init_db(self):
        """Створення всіх таблиць в БД"""
        try:
            from sqlalchemy import inspect
            
            # Перевіряємо, чи таблиці вже існують
            inspector = inspect(self.engine)
            existing_tables = set(inspector.get_table_names())
            
            # Отримуємо список таблиць, які мають бути створені
            expected_tables = set(Base.metadata.tables.keys())
            
            # Створюємо таблиці (якщо вони не існують, create_all їх створить)
            Base.metadata.create_all(bind=self.engine)
            
            # Перевіряємо, чи були створені нові таблиці
            inspector = inspect(self.engine)
            new_tables = set(inspector.get_table_names())
            created_tables = new_tables - existing_tables
            
            # Логуємо тільки якщо були створені нові таблиці
            if created_tables:
                logger.log_info(f"Створено нові таблиці БД: {', '.join(sorted(created_tables))}")
            elif not existing_tables:
                # Якщо таблиць не було взагалі, значить це перша ініціалізація
                logger.log_info("Таблиці БД успішно створені")
            
            # Виконуємо міграції
            self.migrate_add_full_name()
            self.migrate_add_teacher_user_id()
            self.migrate_update_announcements()
            self.migrate_add_password_hash()
            self.migrate_create_groups_table()
            self.migrate_add_group_id_to_schedule()
            self.migrate_add_poll_fields()
            
            # Видаляємо загальні записи без teacher_user_id
            self.migrate_remove_orphaned_entries()
            
            # Створюємо адміністратора за замовчуванням, якщо його немає
            self.create_default_admin()
            
            return True
        except Exception as e:
            logger.log_error(f"Помилка створення таблиць БД: {e}")
            return False
    
    def create_default_admin(self):
        """Створення адміністратора за замовчуванням"""
        try:
            from werkzeug.security import generate_password_hash
            from models import User
            from datetime import datetime
            from sqlalchemy import inspect
            
            # Перевіряємо чи існує таблиця users
            inspector = inspect(self.engine)
            if 'users' not in inspector.get_table_names():
                return
            
            with self.SessionLocal() as session:
                # Перевіряємо чи є адміністратор
                admin = session.query(User).filter(User.role == 'admin').first()
                if admin:
                    # Якщо адмін існує, але без пароля - встановлюємо стандартний
                    if not admin.password_hash:
                        default_password = "admin123"
                        admin.password_hash = generate_password_hash(default_password)
                        session.commit()
                        logger.log_info(f"Встановлено стандартний пароль для адміністратора (User ID: {admin.user_id})")
                    return  # Адмін вже існує
                
                # Перевіряємо чи користувач з ID=1 вже існує
                existing_user = session.query(User).filter(User.user_id == 1).first()
                if existing_user:
                    # Якщо користувач існує, робимо його адміном
                    existing_user.role = 'admin'
                    if not existing_user.password_hash:
                        default_password = "admin123"
                        existing_user.password_hash = generate_password_hash(default_password)
                    if not existing_user.full_name:
                        existing_user.full_name = "Адміністратор"
                    session.commit()
                    logger.log_info(f"Користувач з ID=1 оновлено на адміністратора (пароль: admin123)")
                    return
                
                # Створюємо нового адміна за замовчуванням
                default_password = "admin123"  # Стандартний пароль
                admin_user = User(
                    user_id=1,
                    username="admin",
                    approved_at=datetime.now(),
                    notifications_enabled=False,
                    role='admin',
                    full_name="Адміністратор",
                    password_hash=generate_password_hash(default_password)
                )
                session.add(admin_user)
                session.commit()
                logger.log_info("Створено адміністратора за замовчуванням (User ID: 1, пароль: admin123)")
        except Exception as e:
            logger.log_error(f"Помилка створення адміністратора за замовчуванням: {e}")
    
    def migrate_add_full_name(self):
        """Міграція: додавання колонки full_name до таблиці users"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                # Перевіряємо чи існує таблиця users
                if 'users' not in inspector.get_table_names():
                    return
                
                # Перевіряємо чи існує колонка full_name
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'full_name' not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(200)"))
        except Exception as e:
            logger.log_error(f"Помилка міграції додавання full_name: {e}")
    
    def migrate_add_teacher_user_id(self):
        """Міграція: додавання колонки teacher_user_id до таблиць schedule_entries та academic_periods"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                # Перевіряємо schedule_entries
                if 'schedule_entries' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('schedule_entries')]
                    if 'teacher_user_id' not in columns:
                        conn.execute(text("ALTER TABLE schedule_entries ADD COLUMN teacher_user_id INTEGER"))
                
                # Перевіряємо academic_periods
                if 'academic_periods' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('academic_periods')]
                    if 'teacher_user_id' not in columns:
                        conn.execute(text("ALTER TABLE academic_periods ADD COLUMN teacher_user_id INTEGER"))
        except Exception as e:
            logger.log_error(f"Помилка міграції додавання teacher_user_id: {e}")
    
    def migrate_update_announcements(self):
        """Міграція: оновлення таблиці announcements (додати sent_at, recipient_count)"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                if 'announcements' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('announcements')]
                    
                    # Додаємо sent_at якщо немає
                    if 'sent_at' not in columns:
                        conn.execute(text("ALTER TABLE announcements ADD COLUMN sent_at DATETIME"))
                    
                    # Додаємо recipient_count якщо немає
                    if 'recipient_count' not in columns:
                        conn.execute(text("ALTER TABLE announcements ADD COLUMN recipient_count INTEGER DEFAULT 0"))
        except Exception as e:
            logger.log_error(f"Помилка міграції оновлення announcements: {e}")
    
    def migrate_add_password_hash(self):
        """Міграція: додавання колонки password_hash до таблиці users"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                if 'users' not in inspector.get_table_names():
                    return
                
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'password_hash' not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        except Exception as e:
            logger.log_error(f"Помилка міграції додавання password_hash: {e}")
    
    def migrate_remove_orphaned_entries(self):
        """Міграція: видалення загальних записів без teacher_user_id"""
        try:
            from models import ScheduleEntry, AcademicPeriod
            with self.SessionLocal() as session:
                # Видаляємо заняття без teacher_user_id
                deleted_schedule = session.query(ScheduleEntry).filter(
                    ScheduleEntry.teacher_user_id.is_(None)
                ).delete()
                
                # Видаляємо періоди без teacher_user_id
                deleted_periods = session.query(AcademicPeriod).filter(
                    AcademicPeriod.teacher_user_id.is_(None)
                ).delete()
                
                session.commit()
                
                if deleted_schedule > 0 or deleted_periods > 0:
                    logger.log_info(
                        f"Видалено загальних записів: {deleted_schedule} заняття, {deleted_periods} періодів"
                    )
        except Exception as e:
            logger.log_error(f"Помилка видалення загальних записів: {e}")
    
    def migrate_create_groups_table(self):
        """Міграція: створення таблиці groups"""
        try:
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            
            # Перевіряємо чи існує таблиця groups
            if 'groups' not in inspector.get_table_names():
                # Таблиця буде створена автоматично через Base.metadata.create_all()
                # Але перевіряємо чи вона існує після створення
                logger.log_info("Таблиця groups буде створена через Base.metadata.create_all()")
        except Exception as e:
            logger.log_error(f"Помилка міграції створення таблиці groups: {e}")
    
    def migrate_add_group_id_to_schedule(self):
        """Міграція: додавання колонки group_id до таблиці schedule_entries"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                if 'schedule_entries' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('schedule_entries')]
                    if 'group_id' not in columns:
                        conn.execute(text("ALTER TABLE schedule_entries ADD COLUMN group_id INTEGER"))
                        logger.log_info("Додано колонку group_id до schedule_entries")
        except Exception as e:
            logger.log_error(f"Помилка міграції додавання group_id: {e}")
    
    def migrate_add_poll_fields(self):
        """Міграція: додавання полів expires_at та sent_to_users до таблиці polls"""
        try:
            from sqlalchemy import text, inspect
            with self.engine.begin() as conn:
                inspector = inspect(self.engine)
                
                if 'polls' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('polls')]
                    
                    if 'expires_at' not in columns:
                        conn.execute(text("ALTER TABLE polls ADD COLUMN expires_at DATETIME"))
                        logger.log_info("Додано колонку expires_at до polls")
                    
                    if 'sent_to_users' not in columns:
                        conn.execute(text("ALTER TABLE polls ADD COLUMN sent_to_users BOOLEAN DEFAULT 0"))
                        logger.log_info("Додано колонку sent_to_users до polls")
                    
                    if 'is_anonymous' not in columns:
                        conn.execute(text("ALTER TABLE polls ADD COLUMN is_anonymous BOOLEAN DEFAULT 0"))
                        logger.log_info("Додано колонку is_anonymous до polls")
                    
                    if 'recipient_user_ids' not in columns:
                        conn.execute(text("ALTER TABLE polls ADD COLUMN recipient_user_ids TEXT"))
                        logger.log_info("Додано колонку recipient_user_ids до polls")
        except Exception as e:
            logger.log_error(f"Помилка міграції додавання полів опитування: {e}")
    
    def drop_all_tables(self):
        """Видалення всіх таблиць (використовувати обережно!)"""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.log_info("Всі таблиці БД видалено")
            return True
        except Exception as e:
            logger.log_error(f"Помилка видалення таблиць: {e}")
            return False
    
    @contextmanager
    def get_session(self, max_retries: int = 3) -> Generator[Session, None, None]:
        """
        Context manager для отримання сесії БД з retry logic
        
        Args:
            max_retries: Максимальна кількість спроб при блокуванні БД
        
        Yields:
            Session: SQLAlchemy сесія
            
        Example:
            with db_manager.get_session() as session:
                users = session.query(User).all()
        """
        session = self.SessionLocal()
        retries = 0
        
        while retries < max_retries:
            try:
                yield session
                session.commit()
                break  # Успішно - виходимо
            except (OperationalError, DatabaseError) as e:
                session.rollback()
                error_msg = str(e).lower()
                
                # Перевіряємо чи це помилка блокування
                if 'locked' in error_msg or 'busy' in error_msg or 'database is locked' in error_msg:
                    retries += 1
                    if retries < max_retries:
                        wait_time = 0.5 * retries  # Exponential backoff
                        # Логуємо тільки якщо це не перша спроба або якщо це критична операція
                        if retries > 1:
                            logger.log_warning(f"БД заблокована, спроба {retries}/{max_retries}, очікування {wait_time:.1f}с")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.log_error(f"БД заблокована після {max_retries} спроб: {e}")
                        raise
                else:
                    # Інша помилка БД - не retry
                    logger.log_error(f"Помилка БД: {e}")
                    raise
            except Exception as e:
                session.rollback()
                logger.log_error(f"Помилка в сесії БД: {e}")
                raise
            finally:
                session.close()
    
    def check_connection(self) -> bool:
        """
        Перевірка підключення до БД
        
        Returns:
            True якщо підключення успішне
        """
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.log_error(f"Помилка підключення до БД: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """
        Створення backup бази даних
        
        Args:
            backup_path: Шлях до файлу backup
            
        Returns:
            True якщо backup успішний
        """
        if not self.database_url.startswith("sqlite"):
            logger.log_error("Backup підтримується тільки для SQLite")
            return False
        
        try:
            import shutil
            db_file = self.database_url.replace("sqlite:///", "")
            
            # Створюємо директорію якщо не існує
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            shutil.copy2(db_file, backup_path)
            logger.log_info(f"Backup БД створено: {backup_path}")
            return True
        except Exception as e:
            logger.log_error(f"Помилка створення backup: {e}")
            return False
    
    def restore_database(self, backup_path: str) -> bool:
        """
        Відновлення бази даних з backup
        
        Args:
            backup_path: Шлях до файлу backup
            
        Returns:
            True якщо відновлення успішне
        """
        if not self.database_url.startswith("sqlite"):
            logger.log_error("Restore підтримується тільки для SQLite")
            return False
        
        try:
            import shutil
            db_file = self.database_url.replace("sqlite:///", "")
            
            if not os.path.exists(backup_path):
                logger.log_error(f"Файл backup не знайдено: {backup_path}")
                return False
            
            shutil.copy2(backup_path, db_file)
            logger.log_info(f"БД відновлено з backup: {backup_path}")
            return True
        except Exception as e:
            logger.log_error(f"Помилка відновлення з backup: {e}")
            return False
    
    def get_table_info(self) -> dict:
        """
        Отримання інформації про таблиці БД
        
        Returns:
            Словник з інформацією про таблиці
        """
        info = {}
        
        try:
            with self.get_session() as session:
                from models import (
                    User, PendingRequest, ScheduleEntry, ScheduleMetadata,
                    AcademicPeriod, Announcement, NotificationHistory,
                    NotificationSettings, Log, BotConfig
                )
                
                info['users'] = session.query(User).count()
                info['pending_requests'] = session.query(PendingRequest).count()
                info['schedule_entries'] = session.query(ScheduleEntry).count()
                info['academic_periods'] = session.query(AcademicPeriod).count()
                info['announcements'] = session.query(Announcement).count()
                info['notification_history'] = session.query(NotificationHistory).count()
                info['logs'] = session.query(Log).count()
                info['config_items'] = session.query(BotConfig).count()
                
        except Exception as e:
            logger.log_error(f"Помилка отримання інформації про таблиці: {e}")
        
        return info
    
    def close(self):
        """Закриття підключення до БД"""
        try:
            self.engine.dispose()
            logger.log_info("Підключення до БД закрито")
        except Exception as e:
            logger.log_error(f"Помилка закриття підключення: {e}")


# Глобальний екземпляр менеджера БД
_db_manager: Optional[DatabaseManager] = None


def init_database(database_url: Optional[str] = None) -> DatabaseManager:
    """
    Ініціалізація глобального менеджера БД
    
    Args:
        database_url: URL бази даних
        
    Returns:
        Екземпляр DatabaseManager
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    _db_manager.init_db()
    return _db_manager


def get_db_manager() -> Optional[DatabaseManager]:
    """
    Отримання глобального менеджера БД
    
    Returns:
        Екземпляр DatabaseManager або None
    """
    return _db_manager


@contextmanager
def get_session(max_retries: int = 3) -> Generator[Session, None, None]:
    """
    Shortcut для отримання сесії з глобального менеджера з retry logic
    
    Args:
        max_retries: Максимальна кількість спроб при блокуванні БД
    
    Yields:
        Session: SQLAlchemy сесія
    """
    if _db_manager is None:
        raise RuntimeError("База даних не ініціалізована. Викличте init_database()")
    
    with _db_manager.get_session(max_retries=max_retries) as session:
        yield session


# Функції для тестування та розробки
def reset_database(database_url: Optional[str] = None):
    """
    Повне очищення та перестворення БД (використовувати обережно!)
    
    Args:
        database_url: URL бази даних
    """
    db = DatabaseManager(database_url or os.getenv("DATABASE_URL", "sqlite:///schedule_bot.db"))
    db.drop_all_tables()
    db.init_db()
    logger.log_info("База даних повністю перестворена")


def initialize_default_config():
    """Ініціалізація конфігурації за замовчуванням"""
    try:
        with get_session() as session:
            from models import ScheduleMetadata, BotConfig
            
            # Перевіряємо чи існує метадата
            metadata = session.query(ScheduleMetadata).first()
            if not metadata:
                metadata = ScheduleMetadata(
                    current_week='numerator',
                    group_name='KCM-24-11',
                    academic_year='2025/2026'
                )
                session.add(metadata)
                logger.log_info("Створено метадані розкладу за замовчуванням")
            
            # Додаємо базові конфігурації
            default_configs = [
                ('notification_interval', '60', 'Інтервал перевірки оповіщень (секунди)'),
                ('alert_update_interval', '60', 'Інтервал оновлення статусу тривог (секунди)'),
                ('log_retention_days', '30', 'Час зберігання логів (дні)'),
            ]
            
            for key, value, description in default_configs:
                config = session.query(BotConfig).filter(BotConfig.key == key).first()
                if not config:
                    config = BotConfig(key=key, value=value, description=description)
                    session.add(config)
            
            session.commit()
            logger.log_info("Конфігурація за замовчуванням ініціалізована")
            return True
            
    except Exception as e:
        logger.log_error(f"Помилка ініціалізації конфігурації: {e}")
        return False

