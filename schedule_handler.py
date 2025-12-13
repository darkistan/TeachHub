"""
Модуль роботи з розкладом занять через SQLite БД
Замінює JSON файли на роботу з БД через SQLAlchemy
"""
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Tuple

from database import get_session
from models import ScheduleEntry, ScheduleMetadata, User
from logger import logger


class ScheduleHandler:
    """Клас для роботи з розкладом занять через БД"""
    
    def __init__(self):
        """Ініціалізація обробника розкладу"""
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = 60  # Кеш на 60 секунд
    
    def _get_cached_schedule(self) -> Optional[Dict]:
        """Отримання розкладу з кешу"""
        if self._cache_time and (datetime.now() - self._cache_time).seconds < self._cache_ttl:
            return self._cache
        return None
    
    def _update_cache(self, data: Dict):
        """Оновлення кешу"""
        self._cache = data
        self._cache_time = datetime.now()
    
    def get_current_week_type(self) -> str:
        """
        Отримання поточного типу тижня (numerator/denominator)
        
        Логіка:
        1. Автоматичне визначення з numerator_start_date (якщо встановлено) - перемикається кожну неділю
        2. Значення current_week (якщо автоматичне визначення недоступне)
        3. За замовчуванням "numerator"
        """
        try:
            with get_session() as session:
                metadata = session.query(ScheduleMetadata).first()
                if metadata:
                    # Спочатку намагаємося автоматично визначити на основі дати
                    if metadata.numerator_start_date:
                        auto_week = self._calculate_week_type_from_date(metadata.numerator_start_date)
                        if auto_week:
                            return auto_week
                    
                    # Якщо автоматичне визначення недоступне, використовуємо збережене значення
                    if metadata.current_week and metadata.current_week in ["numerator", "denominator"]:
                        return metadata.current_week
                    
                    # За замовчуванням
                    return "numerator"
                return "numerator"
        except Exception as e:
            logger.log_error(f"Помилка отримання типу тижня: {e}")
            return "numerator"
    
    def _calculate_week_type_from_date(self, numerator_start_date: str) -> Optional[str]:
        """
        Автоматичне визначення типу тижня на основі дати початку відліку
        Перемикається кожну неділю автоматично
        """
        try:
            numerator_start = datetime.strptime(numerator_start_date, "%Y-%m-%d").date()
            current_date = datetime.now().date()
            
            # Знаходимо поточну неділю (початок тижня)
            days_since_sunday = current_date.weekday() + 1  # Днів з неділі (1-7)
            if days_since_sunday == 7:
                # Сьогодні неділя
                current_sunday = current_date
            else:
                # Знаходимо минулу неділю
                current_sunday = current_date - timedelta(days=days_since_sunday)
            
            # Обчислюємо різницю в тижнях між поточною неділею та датою початку
            days_diff = (current_sunday - numerator_start).days
            week_number = days_diff // 7
            
            # Парний номер тижня = чисельник, непарний = знаменник
            return "numerator" if week_number % 2 == 0 else "denominator"
        except Exception as e:
            logger.log_error(f"Помилка автоматичного визначення типу тижня: {e}")
            return None
    
    def set_current_week_type(self, week_type: str) -> bool:
        """Встановлення типу тижня"""
        if week_type not in ["numerator", "denominator"]:
            return False
        
        try:
            with get_session() as session:
                metadata = session.query(ScheduleMetadata).first()
                if not metadata:
                    metadata = ScheduleMetadata(current_week=week_type)
                    session.add(metadata)
                else:
                    metadata.current_week = week_type
                    metadata.last_updated = datetime.now()
                
                session.commit()
                self._cache = {}  # Очищаємо кеш
                logger.log_info(f"Встановлено тип тижня: {week_type}")
                return True
        except Exception as e:
            logger.log_error(f"Помилка встановлення типу тижня: {e}")
            return False
    
    def get_day_schedule(self, day: str, week_type: Optional[str] = None, teacher_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Отримання розкладу на день
        
        Args:
            day: День тижня (monday, tuesday, etc.)
            week_type: Тип тижня (numerator/denominator)
            teacher_user_id: ID викладача для фільтрації (опціонально)
        """
        if week_type is None:
            week_type = self.get_current_week_type()
        
        try:
            with get_session() as session:
                query = session.query(ScheduleEntry).filter(
                    ScheduleEntry.day_of_week == day,
                    ScheduleEntry.week_type == week_type
                )
                
                # Фільтруємо по викладачу, якщо вказано
                if teacher_user_id is not None:
                    query = query.filter(ScheduleEntry.teacher_user_id == teacher_user_id)
                
                entries = query.all()
                
                result = []
                for entry in entries:
                    # Отримуємо ПІБ викладача з User, якщо є teacher_user_id
                    teacher_name = entry.teacher
                    if entry.teacher_user_id:
                        user = session.query(User).filter(User.user_id == entry.teacher_user_id).first()
                        if user and getattr(user, 'full_name', None):
                            teacher_name = user.full_name
                    
                    # Отримуємо інформацію про групу, якщо є group_id
                    group_name = None
                    headman_name = None
                    headman_phone = None
                    if entry.group_id:
                        from models import Group
                        group = session.query(Group).filter(Group.id == entry.group_id).first()
                        if group:
                            group_name = group.name
                            headman_name = group.headman_name
                            headman_phone = group.headman_phone
                    
                    result.append({
                        'time': entry.time,
                        'subject': entry.subject,
                        'type': entry.lesson_type,
                        'teacher': teacher_name,
                        'teacher_user_id': entry.teacher_user_id,
                        'teacher_phone': entry.teacher_phone,
                        'classroom': entry.classroom,
                        'conference_link': entry.conference_link,
                        'exam_type': entry.exam_type,
                        'group_id': entry.group_id,
                        'group_name': group_name,
                        'headman_name': headman_name,
                        'headman_phone': headman_phone
                    })
                
                return result
        except Exception as e:
            logger.log_error(f"Помилка отримання розкладу для {day}, {week_type}: {e}")
            return []
    
    def get_current_day_name(self) -> str:
        """Отримання назви поточного дня"""
        days = {
            0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
            4: "friday", 5: "saturday", 6: "sunday"
        }
        return days[datetime.now().weekday()]
    
    def get_current_lesson_info(self, teacher_user_id: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Отримання інформації про поточне та наступне заняття
        
        Args:
            teacher_user_id: ID викладача для фільтрації (опціонально)
        """
        current_time = datetime.now().time()
        current_day = self.get_current_day_name()
        current_week = self.get_current_week_type()
        
        today_lessons = self.get_day_schedule(current_day, current_week, teacher_user_id)
        
        if not today_lessons:
            return None, None
        
        current_lesson = None
        next_lesson = None
        
        for lesson in today_lessons:
            start_time_str, end_time_str = lesson["time"].split("-")
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            if start_time <= current_time <= end_time:
                current_lesson = lesson
            elif current_time < start_time and next_lesson is None:
                next_lesson = lesson
        
        return current_lesson, next_lesson
    
    def get_lesson_timer_info(self, lesson: Dict[str, Any]) -> Optional[str]:
        """Отримання інформації про таймер до кінця пари"""
        current_time = datetime.now().time()
        start_time_str, end_time_str = lesson["time"].split("-")
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        
        if not (start_time <= current_time <= end_time):
            return None
        
        current_datetime = datetime.combine(datetime.today(), current_time)
        end_datetime = datetime.combine(datetime.today(), end_time)
        
        time_remaining = end_datetime - current_datetime
        total_minutes = int(time_remaining.total_seconds() / 60)
        
        if total_minutes <= 0:
            return None
        
        if total_minutes >= 60:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            time_str = f"{hours}г {minutes}хв" if minutes > 0 else f"{hours}г"
        else:
            time_str = f"{total_minutes} хв"
        
        total_duration = int((end_datetime - datetime.combine(datetime.today(), start_time)).total_seconds() / 60)
        progress = int((total_duration - total_minutes) / total_duration * 20)
        progress = max(0, min(20, progress))
        
        progress_bar = "█" * progress + "░" * (20 - progress)
        
        return f"⏰ До кінця пари: {time_str}\n📊 [{progress_bar}] {progress * 5}%"
    
    def format_lesson_for_display(self, lesson: Dict[str, Any], is_current: bool = False) -> str:
        """Форматування заняття для відображення"""
        if not lesson:
            return ""
        
        status_emoji = "🔴" if is_current else "📚"
        status_text = "ЗАРАЗ" if is_current else ""
        
        meet_link = lesson['conference_link']
        type_emoji = {"лекція": "📚", "практика": "✏️", "лабораторна": "🔬"}.get(lesson["type"], "📖")
        exam_emoji = "✅" if lesson["exam_type"] == "залік" else "📝"
        
        message_parts = []
        if status_text:
            message_parts.append(f"{status_emoji} <b>{status_text}</b>")
        
        message_parts.extend([
            f"{type_emoji} <b>{lesson['subject']}</b> ({lesson['type']})",
            f"🕐 {lesson['time']}",
        ])
        
        # Додаємо інформацію про групу замість викладача
        if lesson.get('group_name'):
            message_parts.append(f"👥 <b>Група:</b> {lesson['group_name']}")
            
            # Додаємо дані старости, якщо вони є
            if lesson.get('headman_name') or lesson.get('headman_phone'):
                headman_info = []
                if lesson.get('headman_name'):
                    headman_info.append(lesson['headman_name'])
                if lesson.get('headman_phone'):
                    headman_info.append(f"<code>{lesson['headman_phone']}</code>")
                if headman_info:
                    message_parts.append(f"👤 <b>Староста:</b> {' | '.join(headman_info)}")
        else:
            message_parts.append(f"👥 <b>Група:</b> не вказана")
        
        message_parts.extend([
            f"💻 <b>Google Meet:</b> <a href='{meet_link}'>Приєднатися</a>",
            f"{exam_emoji} <b>Тип контролю:</b> {lesson['exam_type']}"
        ])
        
        return "\n".join(message_parts)
    
    def get_week_schedule(self, week_type: Optional[str] = None, teacher_user_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Отримання розкладу на тиждень
        
        Args:
            week_type: Тип тижня (numerator/denominator)
            teacher_user_id: ID викладача для фільтрації (опціонально)
        """
        if week_type is None:
            week_type = self.get_current_week_type()
        
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        result = {}
        
        for day in days:
            result[day] = self.get_day_schedule(day, week_type, teacher_user_id)
        
        return result
    
    def _get_day_name_ua(self, day: str) -> str:
        """Отримання назви дня українською мовою"""
        day_names = {
            "monday": "Понеділок", "tuesday": "Вівторок", "wednesday": "Середа",
            "thursday": "Четвер", "friday": "П'ятниця", "saturday": "Субота",
            "sunday": "Неділя"
        }
        return day_names.get(day, day)
    
    def get_week_type_display(self) -> str:
        """Отримання відображення поточного типу тижня"""
        current = self.get_current_week_type()
        return "📚 Тиждень чисельника" if current == "numerator" else "📖 Тиждень знаменника"
    
    def is_connected(self) -> bool:
        """Перевірка чи підключена БД"""
        try:
            with get_session() as session:
                session.query(ScheduleMetadata).first()
                return True
        except Exception as e:
            logger.log_error(f"Помилка підключення до БД: {e}")
            return False


# Глобальний екземпляр обробника розкладу
schedule_handler = None


def init_schedule_handler() -> ScheduleHandler:
    """Ініціалізація глобального обробника розкладу"""
    global schedule_handler
    schedule_handler = ScheduleHandler()
    return schedule_handler


def get_schedule_handler() -> Optional[ScheduleHandler]:
    """Отримання глобального обробника розкладу"""
    return schedule_handler

