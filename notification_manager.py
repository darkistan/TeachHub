"""
Модуль для управління оповіщеннями користувачів через БД
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from database import get_session
from models import User, NotificationHistory, ScheduleEntry, ScheduleMetadata
from logger import logger
from schedule_handler import get_schedule_handler
from air_alert import get_air_alert_manager


class NotificationManager:
    """Менеджер для управління оповіщеннями користувачів через БД"""
    
    def __init__(self):
        """Ініціалізація менеджера оповіщень"""
        self.notification_interval = 60
        self.is_running = False
    
    def set_user_notifications(self, user_id: int, enabled: bool) -> bool:
        """Встановлення статусу оповіщень для користувача"""
        try:
            with get_session() as session:
                user = session.query(User).filter(User.user_id == user_id).first()
                if user:
                    user.notifications_enabled = enabled
                    session.commit()
                logger.log_info(f"Оповіщення для користувача {user_id} {'увімкнені' if enabled else 'вимкнені'}")
                return True
            return False
        except Exception as e:
            logger.log_error(f"Помилка встановлення оповіщень: {e}")
            return False
    
    def get_user_notifications_status(self, user_id: int) -> bool:
        """Отримання статусу оповіщень користувача"""
        try:
            with get_session() as session:
                user = session.query(User).filter(User.user_id == user_id).first()
                return user.notifications_enabled if user else False
        except Exception as e:
            logger.log_error(f"Помилка отримання статусу оповіщень: {e}")
            return False
    
    def get_users_with_notifications(self) -> List[Dict[str, Any]]:
        """Отримання списку користувачів з увімкненими оповіщеннями"""
        try:
            with get_session() as session:
                users = session.query(User).filter(User.notifications_enabled == True).all()
                return [{'user_id': u.user_id, 'username': u.username} for u in users]
        except Exception as e:
            logger.log_error(f"Помилка отримання користувачів з оповіщеннями: {e}")
            return []
    
    def get_next_lesson_info(self, teacher_user_id: int) -> Optional[Dict[str, Any]]:
        """
        Отримання інформації про наступне заняття для конкретного викладача
        
        Args:
            teacher_user_id: ID викладача
        """
        try:
            schedule = get_schedule_handler()
            if not schedule or not schedule.is_connected():
                return None
            
            current_day = schedule.get_current_day_name()
            current_week = schedule.get_current_week_type()
            # Отримуємо розклад тільки для цього викладача
            day_schedule = schedule.get_day_schedule(current_day, current_week, teacher_user_id=teacher_user_id)
            
            if not day_schedule:
                return None
            
            now = datetime.now()
            current_time = now.time()
            
            for lesson in day_schedule:
                lesson_time_str = lesson.get("time", "").split("-")[0]
                try:
                    lesson_time = datetime.strptime(lesson_time_str, "%H:%M").time()
                    if lesson_time > current_time:
                        lesson_datetime = datetime.combine(now.date(), lesson_time)
                        time_until_start = lesson_datetime - now
                        
                        return {
                            "lesson": lesson,
                            "time_until_start": time_until_start,
                            "lesson_datetime": lesson_datetime,
                            "day_name": current_day,
                            "week_type": current_week,
                            "teacher_user_id": teacher_user_id
                        }
                except ValueError:
                    continue
            
            return None
        except Exception as e:
            logger.log_error(f"Помилка отримання наступного заняття для викладача {teacher_user_id}: {e}")
            return None
    
    async def create_notification_message(self, lesson_info: Dict[str, Any]) -> str:
        """Створення повідомлення оповіщення"""
        try:
            lesson = lesson_info["lesson"]
            air_alert_manager = get_air_alert_manager()
            alert_status = await air_alert_manager.get_alert_status()
            
            if alert_status and air_alert_manager.active_alerts:
                alert_types = set(alert.get('alert_type', 'unknown') for alert in air_alert_manager.active_alerts)
                if 'air_raid' in alert_types:
                    alert_header = f"🚨 <b>ПОВІТРЯНА ТРИВОГА В {air_alert_manager.city.upper()}!</b>\n" + "─" * 25 + "\n"
                else:
                    alert_header = f"⚠️ <b>ТРИВОГА В {air_alert_manager.city.upper()}!</b>\n" + "─" * 25 + "\n"
            else:
                alert_header = f"✅ <b>В {air_alert_manager.city.upper()} ТИХО</b>\n" + "─" * 25 + "\n"
            
            subject = lesson.get("subject", "Невідомо")
            lesson_time = lesson.get("time", "Невідомо")
            group_name = lesson.get("group_name", "не вказана")
            headman_name = lesson.get("headman_name")
            headman_phone = lesson.get("headman_phone")
            lesson_type = lesson.get("type", "лекція")
            meet_link = lesson.get("conference_link", "")
            
            type_emoji = {"лекція": "📚", "практика": "✏️", "лабораторна": "🔬"}.get(lesson_type, "📖")
            
            day_names = {
                "monday": "Понеділок", "tuesday": "Вівторок", "wednesday": "Середа",
                "thursday": "Четвер", "friday": "П'ятниця", "saturday": "Субота", "sunday": "Неділя"
            }
            day_name_ua = day_names.get(lesson_info['day_name'], lesson_info['day_name'])
            week_type_display = "🔢 Чисел." if lesson_info['week_type'] == "numerator" else "🔢 Знамен."
            
            message_parts = [
                alert_header,
                f"🔔 <b>НАГАДУВАННЯ ПРО ЗАНЯТТЯ</b>",
                "─" * 30,
                f"📅 <b>{day_name_ua}</b> ({week_type_display})",
                f"⏰ <b>Через ~10 хв</b> починається:",
                "",
                f"{type_emoji} <b>{subject}</b>",
                f"🕐 {lesson_time}",
                f"👥 Група: {group_name}",
            ]
            
            # Додаємо дані старости, якщо вони є
            if headman_name or headman_phone:
                headman_parts = []
                if headman_name:
                    headman_parts.append(headman_name)
                if headman_phone:
                    headman_parts.append(f"<code>{headman_phone}</code>")
                if headman_parts:
                    message_parts.append(f"👤 Староста: {' | '.join(headman_parts)}")
            
            message_parts.append("")
            
            if meet_link:
                message_parts.append(f"💻 <a href='{meet_link}'>Приєднатися до Google Meet</a>")
            
            message_parts.extend(["", "💡 <i>Оповіщення можна вимкнути в меню бота</i>"])
            
            return "\n".join(message_parts)
        except Exception as e:
            logger.log_error(f"Помилка створення повідомлення: {e}")
            return "🔔 Нагадування про заняття"
    
    async def check_and_send_notifications(self, bot) -> None:
        """Перевірка та відправка оповіщень для всіх викладачів"""
        try:
            users = self.get_users_with_notifications()
            if not users:
                return
            
            today = datetime.now().date().isoformat()
            total_sent = 0
            
            # Перевіряємо заняття для кожного викладача окремо
            for user in users:
                try:
                    user_id = user.get("user_id")
                    if not user_id:
                        continue
                    
                    # Отримуємо наступне заняття для цього викладача
                    lesson_info = self.get_next_lesson_info(teacher_user_id=user_id)
                    if not lesson_info:
                        continue
                    
                    time_until_start = lesson_info["time_until_start"]
                    minutes_until_start = int(time_until_start.total_seconds() / 60)
                    lesson = lesson_info["lesson"]
                    
                    # Перевіряємо чи потрібно відправляти (за 10 хвилин)
                    if not (10 <= minutes_until_start <= 11):
                        continue
                    
                    lesson_key = f"{today}_{lesson.get('subject')}_{lesson.get('time')}_{lesson_info['day_name']}_{lesson_info['week_type']}_{user_id}"
                    
                    # Перевіряємо чи вже відправляли
                    with get_session() as session:
                        existing = session.query(NotificationHistory).filter(
                            NotificationHistory.lesson_key == lesson_key,
                            NotificationHistory.notification_date == today,
                            NotificationHistory.user_id == user_id
                        ).first()
                        
                        if existing:
                            continue
                    
                    # Створюємо повідомлення для цього викладача
                    message_text = await self.create_notification_message(lesson_info)
                
                    # Відправляємо оповіщення
                    await bot.send_message(chat_id=user_id, text=message_text, parse_mode='HTML')
                    
                    # Зберігаємо в історію
                    with get_session() as session:
                        history = NotificationHistory(
                            user_id=user_id,
                            lesson_key=lesson_key,
                            sent_at=datetime.now(),
                            notification_date=today
                        )
                        session.add(history)
                        session.commit()
                    
                    total_sent += 1
                    logger.log_info(f"✅ Відправлено оповіщення викладачу {user_id} про '{lesson.get('subject')}'")
                    
                except Exception as e:
                    logger.log_error(f"Помилка відправки оповіщення викладачу {user.get('user_id')}: {e}")
            
            if total_sent > 0:
                logger.log_info(f"✅ Всього відправлено {total_sent} оповіщень")
        except Exception as e:
            logger.log_error(f"Помилка перевірки оповіщень: {e}")
    
    async def start_notification_loop(self, bot) -> None:
        """Запуск циклу перевірки оповіщень"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.log_info("Запуск циклу оповіщень")
        
        while self.is_running:
            try:
                await self.check_and_send_notifications(bot)
                await asyncio.sleep(self.notification_interval)
            except Exception as e:
                logger.log_error(f"Помилка в циклі оповіщень: {e}")
                await asyncio.sleep(60)
    
    def stop_notification_loop(self) -> None:
        """Зупинка циклу оповіщень"""
        self.is_running = False
    
    def reset_notification_history(self) -> None:
        """Скидання історії (очищення старих записів)"""
        try:
            with get_session() as session:
                week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
                deleted = session.query(NotificationHistory).filter(
                    NotificationHistory.notification_date < week_ago
                ).delete()
                session.commit()
                if deleted > 0:
                    logger.log_info(f"Очищено {deleted} старих записів історії")
        except Exception as e:
            logger.log_error(f"Помилка очищення історії: {e}")


# Глобальний екземпляр
notification_manager = NotificationManager()


def get_notification_manager() -> NotificationManager:
    """Отримання глобального менеджера оповіщень"""
    return notification_manager

