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
    
    def get_next_lesson_info(self) -> Optional[Dict[str, Any]]:
        """Отримання інформації про наступне заняття"""
        try:
            schedule = get_schedule_handler()
            if not schedule or not schedule.is_connected():
                return None
            
            current_day = schedule.get_current_day_name()
            current_week = schedule.get_current_week_type()
            day_schedule = schedule.get_day_schedule(current_day, current_week)
            
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
                            "week_type": current_week
                        }
                except ValueError:
                    continue
            
            return None
        except Exception as e:
            logger.log_error(f"Помилка отримання наступного заняття: {e}")
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
            teacher = lesson.get("teacher", "Невідомо")
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
                f"👨‍🏫 {teacher}",
                ""
            ]
            
            if meet_link:
                message_parts.append(f"💻 <a href='{meet_link}'>Приєднатися до Google Meet</a>")
            
            message_parts.extend(["", "💡 <i>Оповіщення можна вимкнути в меню бота</i>"])
            
            return "\n".join(message_parts)
        except Exception as e:
            logger.log_error(f"Помилка створення повідомлення: {e}")
            return "🔔 Нагадування про заняття"
    
    async def check_and_send_notifications(self, bot) -> None:
        """Перевірка та відправка оповіщень"""
        try:
            lesson_info = self.get_next_lesson_info()
            if not lesson_info:
                return
            
            time_until_start = lesson_info["time_until_start"]
            minutes_until_start = int(time_until_start.total_seconds() / 60)
            lesson = lesson_info["lesson"]
            
            today = datetime.now().date().isoformat()
            lesson_key = f"{today}_{lesson.get('subject')}_{lesson.get('time')}_{lesson_info['day_name']}_{lesson_info['week_type']}"
            
            if 10 <= minutes_until_start <= 11:
                # Перевіряємо чи вже відправляли
                with get_session() as session:
                    existing = session.query(NotificationHistory).filter(
                        NotificationHistory.lesson_key == lesson_key,
                        NotificationHistory.notification_date == today
                    ).first()
                    
                    if existing:
                        return
                
                users = self.get_users_with_notifications()
                if not users:
                    return
                
                message_text = await self.create_notification_message(lesson_info)
                
                sent_count = 0
                for user in users:
                    try:
                        user_id = user.get("user_id")
                        if user_id:
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
                            
                            sent_count += 1
                    except Exception as e:
                        logger.log_error(f"Помилка відправки оповіщення {user_id}: {e}")
                
                logger.log_info(f"✅ Відправлено {sent_count} оповіщень про '{lesson.get('subject')}'")
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

