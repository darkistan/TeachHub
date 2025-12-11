"""
Модуль для управління оголошеннями через БД
Оголошення відправляються прямо в чат користувачам через Telegram Bot API
"""
import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from database import get_session
from models import Announcement, AnnouncementRecipient, User
from logger import logger

# Завантажуємо змінні середовища
load_dotenv("config.env")

# Telegram Bot API URL
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


class AnnouncementManager:
    """Клас для управління оголошеннями через БД"""
    
    def __init__(self):
        """Ініціалізація менеджера оголошень"""
        pass
    
    def send_announcement_to_users(
        self, 
        recipient_user_ids: List[int], 
        content: str, 
        priority: str,
        author_id: int, 
        author_username: str
    ) -> Dict[str, Any]:
        """
        Відправка оголошення вибраним користувачам через Telegram Bot API
        
        Args:
            recipient_user_ids: Список user_id отримувачів
            content: Текст оголошення
            priority: Пріоритет (normal, important, urgent)
            author_id: ID автора
            author_username: Username автора
            
        Returns:
            Словник зі статистикою відправки: {'sent': int, 'failed': int, 'announcement_id': int}
        """
        if not TELEGRAM_BOT_TOKEN:
            logger.log_error("TELEGRAM_BOT_TOKEN не встановлено в config.env")
            return {'sent': 0, 'failed': len(recipient_user_ids), 'announcement_id': None}
        
        try:
            with get_session() as session:
                # Створюємо запис оголошення
                announcement = Announcement(
                    content=content,
                    author_id=author_id,
                    author_username=author_username,
                    priority=priority,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    sent_at=datetime.now(),
                    recipient_count=len(recipient_user_ids)
                )
                session.add(announcement)
                session.flush()  # Отримуємо ID без commit
                
                # Формуємо повідомлення з пріоритетом
                priority_emoji = {
                    'urgent': '🔴 ТЕРМІНОВЕ',
                    'important': '🟡 ВАЖЛИВЕ',
                    'normal': '📋 Оголошення'
                }.get(priority, '📋 Оголошення')
                
                message_text = f"{priority_emoji}\n\n{content}\n\n👤 Автор: @{author_username}"
                
                # Відправляємо повідомлення кожному отримувачу
                sent_count = 0
                failed_count = 0
                
                for recipient_id in recipient_user_ids:
                    try:
                        # Відправляємо через Telegram Bot API
                        response = requests.post(
                            f"{TELEGRAM_API_URL}/sendMessage",
                            json={
                                'chat_id': recipient_id,
                                'text': message_text,
                                'parse_mode': 'HTML'
                            },
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            status = 'sent'
                            sent_count += 1
                        else:
                            error_data = response.json()
                            if error_data.get('error_code') == 403:
                                status = 'blocked'  # Користувач заблокував бота
                            else:
                                status = 'failed'
                            failed_count += 1
                            logger.log_warning(f"Помилка відправки оголошення {announcement.id} користувачу {recipient_id}: {error_data.get('description', 'Unknown error')}")
                        
                        # Зберігаємо історію відправки
                        recipient = AnnouncementRecipient(
                            announcement_id=announcement.id,
                            recipient_user_id=recipient_id,
                            sent_at=datetime.now(),
                            status=status
                        )
                        session.add(recipient)
                        
                    except requests.exceptions.RequestException as e:
                        failed_count += 1
                        status = 'failed'
                        logger.log_error(f"Помилка відправки оголошення {announcement.id} користувачу {recipient_id}: {e}")
                        
                        # Зберігаємо історію навіть при помилці
                        recipient = AnnouncementRecipient(
                            announcement_id=announcement.id,
                            recipient_user_id=recipient_id,
                            sent_at=datetime.now(),
                            status=status
                        )
                        session.add(recipient)
                
                # Оновлюємо кількість отримувачів
                announcement.recipient_count = sent_count
                session.commit()
                
                logger.log_info(f"Оголошення {announcement.id} відправлено: {sent_count} успішно, {failed_count} помилок")
                
                return {
                    'sent': sent_count,
                    'failed': failed_count,
                    'announcement_id': announcement.id
                }
            
        except Exception as e:
            logger.log_error(f"Помилка відправки оголошення: {e}")
            return {'sent': 0, 'failed': len(recipient_user_ids), 'announcement_id': None}
    
    def get_announcement_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Отримання історії відправлених оголошень
        
        Args:
            limit: Максимальна кількість записів
            
        Returns:
            Список оголошень з інформацією про відправку
        """
        try:
            with get_session() as session:
                announcements = session.query(Announcement).order_by(
                    Announcement.sent_at.desc()
                ).limit(limit).all()
                
                result = []
                for ann in announcements:
                    result.append({
                        'id': ann.id,
                        'content': ann.content[:100] + '...' if len(ann.content) > 100 else ann.content,
                        'author_username': ann.author_username,
                        'priority': ann.priority,
                        'sent_at': ann.sent_at if ann.sent_at else None,
                        'recipient_count': ann.recipient_count or 0,
                        'created_at': ann.created_at
                    })
                
                return result
        except Exception as e:
            logger.log_error(f"Помилка отримання історії оголошень: {e}")
            return []
    
    def get_announcement_recipients(self, announcement_id: int) -> List[Dict[str, Any]]:
        """
        Отримання списку отримувачів конкретного оголошення
        
        Args:
            announcement_id: ID оголошення
            
        Returns:
            Список отримувачів зі статусом відправки
        """
        try:
            with get_session() as session:
                recipients = session.query(AnnouncementRecipient, User).join(
                    User, AnnouncementRecipient.recipient_user_id == User.user_id
                ).filter(
                    AnnouncementRecipient.announcement_id == announcement_id
                ).all()
                
                result = []
                for recipient, user in recipients:
                    result.append({
                        'recipient_user_id': recipient.recipient_user_id,
                        'username': user.username,
                        'full_name': user.full_name,
                        'sent_at': recipient.sent_at,
                        'status': recipient.status
                    })
                
                return result
        except Exception as e:
            logger.log_error(f"Помилка отримання отримувачів оголошення {announcement_id}: {e}")
            return []
    
    def delete_announcement(self, announcement_id: int) -> bool:
        """Видалення оголошення та всіх пов'язаних записів"""
        try:
            with get_session() as session:
                # Видаляємо отримувачів
                session.query(AnnouncementRecipient).filter(
                    AnnouncementRecipient.announcement_id == announcement_id
                ).delete()
                
                # Видаляємо оголошення
                announcement = session.query(Announcement).filter(Announcement.id == announcement_id).first()
                if announcement:
                    session.delete(announcement)
                    session.commit()
                logger.log_info(f"Видалено оголошення {announcement_id}")
                return True
            return False
        except Exception as e:
            logger.log_error(f"Помилка видалення оголошення: {e}")
            return False
    
    def get_all_teachers(self) -> List[Dict[str, Any]]:
        """
        Отримання списку всіх викладачів (всі користувачі)
        
        Returns:
            Список викладачів з user_id, username та full_name
        """
        try:
            with get_session() as session:
                # Отримуємо всіх користувачів (не тільки з role='user')
                teachers = session.query(User).all()
                
                result = []
                for teacher in teachers:
                    result.append({
                        'user_id': teacher.user_id,
                        'username': teacher.username or f"user_{teacher.user_id}",
                        'full_name': getattr(teacher, 'full_name', None)
                    })
                
                return result
        except Exception as e:
            logger.log_error(f"Помилка отримання списку викладачів: {e}")
            return []
        

# Глобальний екземпляр
announcement_manager = AnnouncementManager()


def get_announcement_manager() -> AnnouncementManager:
    """Отримання глобального менеджера оголошень"""
    return announcement_manager
