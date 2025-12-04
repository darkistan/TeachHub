"""
Модуль для управління оголошеннями через БД
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import get_session
from models import Announcement, User
from logger import logger
from csrf_manager import csrf_manager


class AnnouncementManager:
    """Клас для управління оголошеннями через БД"""
    
    def __init__(self):
        """Ініціалізація менеджера оголошень"""
        pass
    
    def create_announcement(self, content: str, author_id: int, author_username: str, priority: str = 'normal') -> bool:
        """Створення нового оголошення"""
        try:
            with get_session() as session:
                # Деактивуємо всі попередні оголошення
                session.query(Announcement).update({'is_active': False})
                
                announcement = Announcement(
                    content=content,
                    author_id=author_id,
                    author_username=author_username,
                    priority=priority,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    is_active=True
                )
                session.add(announcement)
                session.commit()
                
                logger.log_info(f"Створено оголошення адміном {author_username}")
                return True
        except Exception as e:
            logger.log_error(f"Помилка створення оголошення: {e}")
            return False
    
    def update_announcement(self, announcement_id: int, content: str, author_id: int, author_username: str) -> bool:
        """Оновлення існуючого оголошення"""
        try:
            with get_session() as session:
                announcement = session.query(Announcement).filter(Announcement.id == announcement_id).first()
                if announcement:
                    announcement.content = content
                    announcement.author_id = author_id
                    announcement.author_username = author_username
                    announcement.updated_at = datetime.now()
                    session.commit()
                    
                    logger.log_info(f"Оновлено оголошення {announcement_id}")
                    return True
                return False
        except Exception as e:
            logger.log_error(f"Помилка оновлення оголошення: {e}")
            return False
    
    def delete_announcement(self, announcement_id: int) -> bool:
        """Видалення оголошення"""
        try:
            with get_session() as session:
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
    
    def get_current_announcement(self) -> Optional[Dict[str, Any]]:
        """Отримання поточного активного оголошення"""
        try:
            with get_session() as session:
                announcement = session.query(Announcement).filter(Announcement.is_active == True).first()
                if announcement:
                    return {
                        'id': announcement.id,
                        'content': announcement.content,
                        'author_id': announcement.author_id,
                        'author_username': announcement.author_username,
                        'priority': announcement.priority,
                        'created_at': announcement.created_at.isoformat(),
                        'updated_at': announcement.updated_at.isoformat()
                    }
                return None
        except Exception as e:
            logger.log_error(f"Помилка отримання оголошення: {e}")
            return None
    
    def create_announcement_keyboard(self, user_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
        """Створення клавіатури для перегляду оголошення"""
        keyboard = []
        
        if is_admin:
            current = self.get_current_announcement()
            if current:
                keyboard.extend([
                    [InlineKeyboardButton("✏️ Редагувати оголошення", 
                                        callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_edit"))],
                    [InlineKeyboardButton("🗑️ Видалити оголошення", 
                                        callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_delete"))],
                    [InlineKeyboardButton("📢 Надіслати сповіщення", 
                                        callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_notify"))]
                ])
            else:
                keyboard.append([InlineKeyboardButton("➕ Створити оголошення", 
                                                    callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_create"))])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад в меню", 
                                            callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))])
        
        return InlineKeyboardMarkup(keyboard)
    
    def create_announcement_management_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Створення клавіатури для управління оголошеннями"""
        current = self.get_current_announcement()
        keyboard = []
        
        if current:
            keyboard.extend([
                [InlineKeyboardButton("✏️ Редагувати", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_edit"))],
                [InlineKeyboardButton("🗑️ Видалити", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_delete"))],
                [InlineKeyboardButton("📢 Надіслати", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_notify"))]
            ])
        else:
            keyboard.append([InlineKeyboardButton("➕ Створити", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_create"))])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_admin"))])
        
        return InlineKeyboardMarkup(keyboard)
    
    def format_announcement_message(self) -> str:
        """Формування повідомлення з оголошенням"""
        current = self.get_current_announcement()
        
        if not current:
            return "📋 **Дошка оголошень**\n\n📭 Оголошень поки немає."
        
        content = current["content"]
        created_at = datetime.fromisoformat(current["created_at"]).strftime("%d.%m.%Y %H:%M")
        updated_at = datetime.fromisoformat(current["updated_at"]).strftime("%d.%m.%Y %H:%M")
        author = current["author_username"]
        
        escaped_content = self._escape_markdown(content)
        escaped_author = self._escape_markdown(author)
        
        date_info = f"📅 Створено: {created_at}"
        if created_at != updated_at:
            date_info += f"\n✏️ Оновлено: {updated_at}"
        
        return "\n".join([
            "📋 **Дошка оголошень**",
            "─" * 25,
            "",
            escaped_content,
            "",
            "─" * 25,
            f"👤 Автор: @{escaped_author}",
            date_info
        ])
    
    def _escape_markdown(self, text: str) -> str:
        """Екранування спеціальних символів Markdown"""
        if not text:
            return text
        
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def send_notification_to_all_users(self, bot, users: List[Dict[str, Any]]) -> int:
        """Надсилання сповіщення про оголошення всім користувачам"""
        current = self.get_current_announcement()
        if not current:
            return 0
        
        notification_text = (
            "📢 **ОНОВЛЕННЯ НА ДОШЦІ ОГОЛОШЕНЬ**\n\n"
            "У дошці оголошень є нове або оновлене оголошення\\!\n\n"
            "Натисніть /menu та виберіть '📋 Дошка оголошень' для перегляду\\."
        )
        
        sent_count = 0
        for user in users:
            try:
                user_id = user.get("user_id")
                if user_id:
                    await bot.send_message(chat_id=user_id, text=notification_text, parse_mode='Markdown')
                    sent_count += 1
            except Exception as e:
                logger.log_error(f"Помилка відправки сповіщення {user_id}: {e}")
        
        logger.log_info(f"Відправлено {sent_count} сповіщень про оголошення")
        return sent_count


# Глобальний екземпляр
announcement_manager = AnnouncementManager()


def get_announcement_manager() -> AnnouncementManager:
    """Отримання глобального менеджера оголошень"""
    return announcement_manager

