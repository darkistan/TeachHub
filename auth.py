"""
Модуль авторизації для Telegram-бота розкладу з SQLite
Замінює JSON файли на роботу з БД через SQLAlchemy
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_session
from models import User, PendingRequest
from logger import logger
from csrf_manager import csrf_manager


class AuthManager:
    """Клас для управління авторизацією користувачів через БД"""
    
    def __init__(self):
        """Ініціалізація менеджера авторизації"""
        pass
    
    def is_user_allowed(self, user_id: int) -> bool:
        """
        Перевірка чи дозволений користувач
        
        Args:
            user_id: ID користувача
            
        Returns:
            True якщо користувач дозволений
        """
        try:
            with get_session() as session:
                user = session.query(User).filter(User.user_id == user_id).first()
                return user is not None
        except Exception as e:
            logger.log_error(f"Помилка перевірки доступу користувача {user_id}: {e}")
            return False
    
    def add_user_request(self, user_id: int, username: str) -> bool:
        """
        Додавання запиту на доступ
        
        Args:
            user_id: ID користувача
            username: Ім'я користувача
            
        Returns:
            True якщо запит додано
        """
        try:
            with get_session() as session:
                # Перевіряємо чи вже є запит
                existing = session.query(PendingRequest).filter(
                    PendingRequest.user_id == user_id
                ).first()
                
                if existing:
                    return False
                
                # Додаємо новий запит
                request = PendingRequest(
                    user_id=user_id,
                    username=username,
                    timestamp=datetime.now()
                )
                session.add(request)
                session.commit()
                
                logger.log_access_request(user_id, username)
                return True
                
        except Exception as e:
            logger.log_error(f"Помилка додавання запиту для {user_id}: {e}")
            return False
    
    def approve_user(self, user_id: int, username: str) -> bool:
        """
        Схвалення користувача
        
        Args:
            user_id: ID користувача
            username: Ім'я користувача
            
        Returns:
            True якщо користувач був схвалений
        """
        try:
            with get_session() as session:
                # Видаляємо з pending_requests
                session.query(PendingRequest).filter(
                    PendingRequest.user_id == user_id
                ).delete()
                
                # Перевіряємо чи вже існує
                existing = session.query(User).filter(User.user_id == user_id).first()
                if existing:
                    return False
                
                # Додаємо до дозволених
                user = User(
                    user_id=user_id,
                    username=username,
                    approved_at=datetime.now(),
                    notifications_enabled=False
                )
                session.add(user)
                session.commit()
                
                logger.log_access_granted(user_id, username)
                return True
                
        except Exception as e:
            logger.log_error(f"Помилка схвалення користувача {user_id}: {e}")
            return False
    
    def deny_user(self, user_id: int, username: str) -> bool:
        """
        Відхилення користувача
        
        Args:
            user_id: ID користувача
            username: Ім'я користувача
            
        Returns:
            True якщо запит був відхилений
        """
        try:
            with get_session() as session:
                deleted = session.query(PendingRequest).filter(
                    PendingRequest.user_id == user_id
                ).delete()
                session.commit()
                
                if deleted > 0:
                    logger.log_access_denied(user_id, username)
                    return True
                return False
                
        except Exception as e:
            logger.log_error(f"Помилка відхилення користувача {user_id}: {e}")
            return False
    
    def revoke_user_access(self, user_id: int) -> bool:
        """
        Відкликання доступу користувача
        
        Args:
            user_id: ID користувача
            
        Returns:
            True якщо доступ був відкликаний
        """
        try:
            with get_session() as session:
                deleted = session.query(User).filter(User.user_id == user_id).delete()
                session.commit()
                
                return deleted > 0
                
        except Exception as e:
            logger.log_error(f"Помилка відкликання доступу {user_id}: {e}")
            return False
    
    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """
        Отримання списку очікуючих запитів
        
        Returns:
            Список запитів
        """
        try:
            with get_session() as session:
                requests = session.query(PendingRequest).all()
                return [
                    {
                        'user_id': req.user_id,
                        'username': req.username,
                        'timestamp': req.timestamp.isoformat() if req.timestamp else None
                    }
                    for req in requests
                ]
        except Exception as e:
            logger.log_error(f"Помилка отримання запитів: {e}")
            return []
    
    def get_allowed_users(self) -> List[Dict[str, Any]]:
        """
        Отримання списку дозволених користувачів
        
        Returns:
            Список користувачів
        """
        try:
            with get_session() as session:
                users = session.query(User).all()
                return [
                    {
                        'user_id': user.user_id,
                        'username': user.username,
                        'approved_at': user.approved_at.isoformat() if user.approved_at else None,
                        'notifications_enabled': user.notifications_enabled
                    }
                    for user in users
                ]
        except Exception as e:
            logger.log_error(f"Помилка отримання користувачів: {e}")
            return []
    
    def create_users_management_keyboard(self, users: List[Dict[str, Any]], page: int = 0, 
                                        items_per_page: int = 10, admin_user_id: int = None) -> InlineKeyboardMarkup:
        """
        Створення клавіатури для управління користувачами
        
        Args:
            users: Список користувачів
            page: Номер сторінки
            items_per_page: Кількість елементів на сторінці
            admin_user_id: ID адміністратора для CSRF токенів
            
        Returns:
            InlineKeyboardMarkup з користувачами та кнопками видалення
        """
        if not users:
            return InlineKeyboardMarkup([])
        
        # Розраховуємо загальну кількість сторінок
        total_pages = (len(users) - 1) // items_per_page + 1
        
        # Обмежуємо номер сторінки
        page = max(0, min(page, total_pages - 1))
        
        # Отримуємо елементи для поточної сторінки
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_users = users[start_idx:end_idx]
        
        # Створюємо кнопки для користувачів
        keyboard = []
        for i, user in enumerate(page_users):
            username = user.get("username", "без username")
            user_id = user.get("user_id", "невідомий")
            
            # Обмежуємо довжину username
            display_username = username
            if len(display_username) > 15:
                display_username = display_username[:12] + "..."
            
            button_text = f"🗑️ {display_username} ({user_id})"
            callback_data = f"rm_{user_id}"
            
            # Додаємо CSRF токен якщо є admin_user_id
            if admin_user_id:
                callback_data = csrf_manager.add_csrf_to_callback_data(admin_user_id, callback_data)
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Додаємо кнопки навігації якщо потрібно
        if total_pages > 1:
            nav_buttons = []
            
            # Кнопка "Назад" (попередня сторінка)
            if page > 0:
                callback_data = f"up_{page-1}"
                if admin_user_id:
                    callback_data = csrf_manager.add_csrf_to_callback_data(admin_user_id, callback_data)
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=callback_data))
            
            # Інформація про сторінку
            callback_data = "upi"
            if admin_user_id:
                callback_data = csrf_manager.add_csrf_to_callback_data(admin_user_id, callback_data)
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=callback_data))
            
            # Кнопка "Вперед" (наступна сторінка)
            if page < total_pages - 1:
                callback_data = f"up_{page+1}"
                if admin_user_id:
                    callback_data = csrf_manager.add_csrf_to_callback_data(admin_user_id, callback_data)
                nav_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=callback_data))
            
            keyboard.append(nav_buttons)
        
        # Додаємо кнопку "Назад до меню"
        callback_data = "back_to_menu"
        if admin_user_id:
            callback_data = csrf_manager.add_csrf_to_callback_data(admin_user_id, callback_data)
        keyboard.append([InlineKeyboardButton("🔙 Назад до меню", callback_data=callback_data)])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def send_access_request_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int) -> None:
        """
        Відправка запиту на доступ адміністратору
        
        Args:
            update: Об'єкт оновлення Telegram
            context: Контекст бота
            admin_id: ID адміністратора
        """
        user = update.effective_user
        username = user.username or "без username"
        
        # Додаємо запит
        self.add_user_request(user.id, username)
        
        # Створюємо inline клавіатуру з CSRF токенами
        approve_callback = csrf_manager.add_csrf_to_callback_data(admin_id, f"approve_{user.id}")
        deny_callback = csrf_manager.add_csrf_to_callback_data(admin_id, f"deny_{user.id}")
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Разрешить", callback_data=approve_callback),
                InlineKeyboardButton("❌ Отклонить", callback_data=deny_callback)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Відправляємо повідомлення адміну
        message_text = (
            f"📢 Новый запрос на доступ к розкладу\\n"
            f"👤 Пользователь: @{username}\\n"
            f"🆔 ID: {user.id}\\n\\n"
            f"Разрешить доступ к розкладу занятий?"
        )
        
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.log_error(f"Помилка відправки запиту адміну: {e}")
    
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обробка callback від адміністратора
        
        Args:
            update: Об'єкт оновлення Telegram
            context: Контекст бота
        """
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        # CSRF захист для callback запитів
        if "|csrf:" in data:
            # Витягуємо оригінальні дані з перевіркою CSRF
            original_data = csrf_manager.extract_callback_data(user_id, data)
            if not original_data:
                await query.edit_message_text("❌ Невірний токен безпеки. Спробуйте ще раз.")
                return
            data = original_data
        else:
            # Для старих callback без CSRF токенів
            logger.log_error(f"Callback без CSRF токена для користувача {user_id}: {data}")
            await query.edit_message_text("❌ Помилка безпеки. Спробуйте ще раз.")
            return
        
        if data.startswith("approve_"):
            target_user_id = int(data.split("_")[1])
            # Знаходимо username з pending_requests
            username = "невідомий"
            pending = self.get_pending_requests()
            for req in pending:
                if req["user_id"] == target_user_id:
                    username = req["username"]
                    break
            
            if self.approve_user(target_user_id, username):
                # Логуємо адмін дію
                logger.log_admin_approve(user_id, target_user_id, username)
                await query.edit_message_text(f"✅ Доступ до розкладу надано користувачу @{username}")
                # Повідомляємо користувача
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="✅ Ваш запит на доступ схвалено! Тепер ви можете використовувати бота для перегляду розкладу."
                    )
                except Exception as e:
                    logger.log_error(f"Помилка відправки повідомлення користувачу: {e}")
            else:
                await query.edit_message_text("❌ Помилка при наданні доступу")
        
        elif data.startswith("deny_"):
            target_user_id = int(data.split("_")[1])
            # Знаходимо username з pending_requests
            username = "невідомий"
            pending = self.get_pending_requests()
            for req in pending:
                if req["user_id"] == target_user_id:
                    username = req["username"]
                    break
            
            if self.deny_user(target_user_id, username):
                # Логуємо адмін дію
                logger.log_admin_deny(user_id, target_user_id, username)
                await query.edit_message_text(f"❌ Доступ відхилено для користувача @{username}")
                # Повідомляємо користувача
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="❌ Доступ отклонён администратором."
                    )
                except Exception as e:
                    logger.log_error(f"Помилка відправки повідомлення користувачу: {e}")
            else:
                await query.edit_message_text("❌ Помилка при відхиленні доступу")


# Глобальний екземпляр менеджера авторизації
auth_manager = AuthManager()

