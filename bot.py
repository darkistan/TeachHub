#!/usr/bin/env python3
"""
Telegram бот для розкладу занять студентів
"""
import os
import asyncio
import logging
from typing import Optional
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from auth import auth_manager
from schedule_handler import init_schedule_handler, get_schedule_handler
from logger import logger
from csrf_manager import csrf_manager
from input_validator import input_validator
from air_alert import get_air_alert_manager
from notification_manager import get_notification_manager
from announcement_manager import get_announcement_manager
from schedule_analyzer import ScheduleAnalyzer
from database import init_database

# Завантажуємо змінні середовища
load_dotenv("config.env")

# Конфігурація
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID", "0")
try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
except ValueError:
    print(f"[ERROR] ADMIN_USER_ID must be a number, got: '{ADMIN_USER_ID_STR}'")
    print("[ERROR] Check config.env file")
    exit(1)

# Глобальні змінні для зберігання результатів
current_week_type = {}
current_day = {}


async def get_air_alert_header() -> str:
    """
    Отримання заголовка з індикацією повітряної тривоги та типу неділі
    
    Returns:
        Рядок з індикацією тривоги та типу неділі
    """
    try:
        air_alert_manager = get_air_alert_manager()
        alert_status = await air_alert_manager.get_alert_status()
        
        # Отримуємо тип поточної неділі
        schedule = get_schedule_handler()
        week_type_display = schedule.get_week_type_display() if schedule else "🔢 Невідомо"
        
        if alert_status and air_alert_manager.active_alerts:
            # Отримуємо типи тривог
            alert_types = set(alert.get('alert_type', 'unknown') for alert in air_alert_manager.active_alerts)
            
            # Визначаємо емоцію залежно від типу тривоги
            if 'air_raid' in alert_types:
                emoji = "🚨"
                alert_text = "ПОВІТРЯНА ТРИВОГА"
            elif 'artillery_shelling' in alert_types:
                emoji = "💥"
                alert_text = "АРТИЛЕРІЙСЬКИЙ ОБСТРІЛ"
            elif 'urban_fights' in alert_types:
                emoji = "⚔️"
                alert_text = "МІСЬКІ БОЇ"
            else:
                emoji = "⚠️"
                alert_text = "ТРИВОГА"
            
            return f"{emoji} <b>{alert_text} В {air_alert_manager.city.upper()}!</b>\n{week_type_display}\n" + "─" * 25 + "\n"
        else:
            return f"✅ <b>В {air_alert_manager.city.upper()} ТИХО</b>\n{week_type_display}\n" + "─" * 25 + "\n"
    except Exception as e:
        logger.log_error(f"Помилка отримання статусу тривоги: {e}")
        return "❓ <b>Статус недоступний</b>\n" + "─" * 20 + "\n"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка команди /start"""
    user = update.effective_user
    user_id = user.id
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    if auth_manager.is_user_allowed(user_id):
        # Показуємо меню для авторизованого користувача
        keyboard = create_menu_keyboard(user_id)
        
        if user_id == ADMIN_USER_ID:
            message_text = alert_header + "👑 Ви адміністратор розкладу"
        else:
            message_text = alert_header + "✅ Ви маєте доступ до розкладу занять"
        
        await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='HTML')
    else:
        # Показуємо меню для неавторизованого користувача
        keyboard = create_menu_keyboard(user_id)
        message_text = alert_header + "🔐 Для доступу до розкладу потрібна авторизація"
        
        await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='HTML')


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка команди /schedule"""
    user_id = update.effective_user.id
    
    if not auth_manager.is_user_allowed(user_id):
        logger.log_unauthorized_access_attempt(user_id, "/schedule")
        await update.message.reply_text("❌ У вас немає доступу до розкладу.")
        return
    
    schedule = get_schedule_handler()
    
    if not schedule or not schedule.is_connected():
        await update.message.reply_text("❌ Розклад недоступний.")
        return
    
    # Показуємо поточний день з розкладом
    await show_current_day_schedule(update, context, user_id)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка команди /today"""
    user_id = update.effective_user.id
    
    if not auth_manager.is_user_allowed(user_id):
        logger.log_unauthorized_access_attempt(user_id, "/today")
        await update.message.reply_text("❌ У вас немає доступу до розкладу.")
        return
    
    schedule = get_schedule_handler()
    
    if not schedule or not schedule.is_connected():
        await update.message.reply_text("❌ Розклад недоступний.")
        return
    
    await show_current_day_schedule(update, context, user_id)


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка команди /week"""
    user_id = update.effective_user.id
    
    if not auth_manager.is_user_allowed(user_id):
        logger.log_unauthorized_access_attempt(user_id, "/week")
        await update.message.reply_text("❌ У вас немає доступу до розкладу.")
        return
    
    schedule = get_schedule_handler()
    
    if not schedule or not schedule.is_connected():
        await update.message.reply_text("❌ Розклад недоступний.")
        return
    
    # Показуємо розклад на тиждень
    await show_week_schedule(update, context, user_id)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка команди /admin"""
    user_id = update.effective_user.id
    
    # Перевіряємо, чи це адміністратор
    if user_id != ADMIN_USER_ID:
        logger.log_unauthorized_access_attempt(user_id, "/admin")
        await update.message.reply_text("❌ У вас немає прав адміністратора.")
        return
    
    # Логуємо доступ до адмін панелі
    logger.log_admin_panel_access(user_id)
    
    # Отримуємо список користувачів
    users = auth_manager.get_allowed_users()
    pending_requests = auth_manager.get_pending_requests()
    
    # Створюємо клавіатуру для управління користувачами
    keyboard = create_admin_keyboard(ADMIN_USER_ID, len(users), len(pending_requests))
    
    message_text = (
        f"📋 **Панель адміністратора розкладу**\n\n"
        f"👥 Користувачі з доступом: {len(users)}\n"
        f"⏳ Очікують схвалення: {len(pending_requests)}"
    )
    
    await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='Markdown')


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда меню з кнопками"""
    user_id = update.effective_user.id
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    # Створюємо клавіатуру залежно від ролі користувача
    keyboard = create_menu_keyboard(user_id)
    
    if auth_manager.is_user_allowed(user_id):
        # Авторизований користувач
        if user_id == ADMIN_USER_ID:
            # Адміністратор
            message_text = alert_header + "👑 Ви адміністратор розкладу"
        else:
            # Звичайний користувач
            message_text = alert_header + "✅ Ви маєте доступ до розкладу занять"
    else:
        # Неавторизований користувач
        message_text = alert_header + "🔐 Для доступу до розкладу потрібна авторизація"
    
    await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='HTML')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда довідки"""
    user_id = update.effective_user.id
    
    if not auth_manager.is_user_allowed(user_id):
        logger.log_unauthorized_access_attempt(user_id, "/help")
        await update.message.reply_text("❌ У вас немає доступу до розкладу.")
        return
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    help_text = alert_header + """
🤖 <b>Telegram Bot Розкладу Занять - Довідка</b>

<b>Основні команди:</b>
• <code>/start</code> - перевірка доступу та початок роботи
• <code>/schedule</code> - поточний розклад на сьогодні
• <code>/today</code> - розклад на сьогодні
• <code>/week</code> - розклад на тиждень
• <code>/menu</code> - головне меню
• <code>/help</code> - ця довідка

<b>Для адміністратора:</b>
• <code>/admin</code> - панель управління користувачами

<b>Як користуватися:</b>

📅 <b>Поточний розклад:</b>
• Натисніть "Сьогодні" щоб побачити розклад на сьогодні
• Поточне заняття виділяється червоним кольором
• Наступне заняття виділяється жовтим кольором
• Таймер показує час до кінця поточної пари

📆 <b>Розклад на тиждень:</b>
• Натисніть "Тиждень" щоб побачити весь розклад
• Можна переключатися між чисельником та знаменником
• Кожне заняття має посилання на Google Meet

📊 <b>Прогрес навчання:</b>
• Натисніть "Прогрес навчання" для аналізу навчального року
• Візуальні прогрес-бари показують завершення кожного періоду
• Детальний графік навчання з датами та періодами
• Відсотки прогресу розраховуються автоматично

📋 <b>Дошка оголошень:</b>
• Натисніть "Дошка оголошень" щоб переглянути актуальні оголошення
• Адміністратор може створювати, редагувати та видаляти оголошення
• При оновленні оголошення всі користувачі отримують сповіщення

🔔 <b>Сповіщення:</b>
• Нагадування про заняття за 10 хвилин до початку
• Можна увімкнути/вимкнути в меню
• Сповіщення надсилаються тільки авторизованим користувачам

💻 <b>Google Meet:</b>
• Кожне заняття має посилання на Google Meet
• Натисніть "Приєднатися" щоб відкрити конференцію
• Посилання автоматично генеруються з коду заняття

🚨 <b>Повітряні тривоги:</b>
• Статус тривог відображається в шапці кожного повідомлення
• Оновлення кожну хвилину для міста Дніпро
• Різні типи тривог: повітряна, артилерійська, міські бої

<b>Примітки:</b>
• Розклад автоматично показує поточний тип тижня
• Всі дії логуються для безпеки
• Для доступу потрібне схвалення адміністратора
• Бот працює 24/7 та автоматично оновлює дані
    """
    
    await update.message.reply_text(help_text, parse_mode='HTML')


async def show_current_day_schedule_alternate(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, week_type: str) -> None:
    """Показ розкладу на поточний день для альтернативного типу тижня"""
    schedule = get_schedule_handler()
    current_day_name = schedule.get_current_day_name()
    
    # Отримуємо розклад для альтернативного типу тижня
    lessons = schedule.get_day_schedule(current_day_name, week_type)
    
    # Формуємо повідомлення
    day_name_ua = schedule._get_day_name_ua(current_day_name)
    week_type_display = "📖 Тиждень знаменника" if week_type == "denominator" else "📚 Тиждень чисельника"
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📅 **{day_name_ua}** ({week_type_display})",
        "─" * 30
    ]
    
    if lessons:
        message_parts.append("📚 **Заняття на день:**")
        message_parts.append("")
        for i, lesson in enumerate(lessons):
            message_parts.append(schedule.format_lesson_for_display(lesson, is_current=False))
            # Додаємо розділювач між лекціями (крім останньої)
            if i < len(lessons) - 1:
                message_parts.append("─" * 20)
    else:
        message_parts.append("📚 **Занять на цей день немає**")
    
    # Створюємо клавіатуру
    keyboard = create_alternate_schedule_keyboard(user_id, current_day_name, week_type)
    
    message_text = "\n".join(message_parts)
    
    # Перевіряємо чи це callback чи команда
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            logger.log_error(f"Помилка редагування повідомлення: {e}")
            # Якщо не вдалося відредагувати, відправляємо нове
            await update.callback_query.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)


async def show_current_day_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Показ розкладу на поточний день"""
    schedule = get_schedule_handler()
    current_day_name = schedule.get_current_day_name()
    current_week = schedule.get_current_week_type()
    
    # Отримуємо інформацію про поточне та наступне заняття
    current_lesson, next_lesson = schedule.get_current_lesson_info()
    
    # Формуємо повідомлення
    day_name_ua = schedule._get_day_name_ua(current_day_name)
    week_type_display = schedule.get_week_type_display()
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📅 **{day_name_ua}** ({week_type_display})",
        "─" * 30
    ]
    
    # Показуємо поточне заняття
    if current_lesson:
        message_parts.append(schedule.format_lesson_for_display(current_lesson, is_current=True))
        
        # Додаємо таймер до кінця пари
        timer_info = schedule.get_lesson_timer_info(current_lesson)
        if timer_info:
            message_parts.append("")
            message_parts.append(timer_info)
        
        message_parts.append("")
    else:
        message_parts.append("🟢 **Поточних занять немає**")
        message_parts.append("")
    
    # Показуємо наступне заняття
    if next_lesson:
        message_parts.append(schedule.format_lesson_for_display(next_lesson, is_current=False))
    else:
        # Показуємо всі заняття на день якщо немає наступного
        lessons = schedule.get_day_schedule(current_day_name, current_week)
        if lessons:
            message_parts.append("📚 **Всі заняття на день:**")
            message_parts.append("")
            for i, lesson in enumerate(lessons):
                message_parts.append(schedule.format_lesson_for_display(lesson, is_current=False))
                # Додаємо розділювач між лекціями (крім останньої)
                if i < len(lessons) - 1:
                    message_parts.append("─" * 20)
        else:
            message_parts.append("📚 **Занять на сьогодні немає**")
    
    # Створюємо клавіатуру
    keyboard = create_schedule_keyboard(user_id, current_day_name, current_week)
    
    message_text = "\n".join(message_parts)
    
    # Перевіряємо чи це callback чи команда
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            logger.log_error(f"Помилка редагування повідомлення: {e}")
            # Якщо не вдалося відредагувати, відправляємо нове
            await update.callback_query.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)


async def show_week_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, week_type: Optional[str] = None) -> None:
    """Показ розкладу на тиждень"""
    schedule = get_schedule_handler()
    if week_type is None:
        current_week = schedule.get_current_week_type()
    else:
        current_week = week_type
    
    week_type_display = "📖 Тиждень знаменника" if current_week == "denominator" else "📚 Тиждень чисельника"
    
    # Отримуємо розклад на тиждень
    week_schedule = schedule.get_week_schedule(current_week)
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📆 **Розклад на тиждень** ({week_type_display})",
        "─" * 40
    ]
    
    days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    for day in days_order:
        if day in week_schedule and week_schedule[day]:
            day_name_ua = schedule._get_day_name_ua(day)
            message_parts.append(f"📅 **{day_name_ua}**")
            
            for i, lesson in enumerate(week_schedule[day]):
                # Показуємо тільки основну інформацію для розкладу на тиждень
                type_emoji = {"лекція": "📚", "практика": "✏️", "лабораторна": "🔬"}.get(lesson["type"], "📖")
                exam_emoji = "✅" if lesson["exam_type"] == "залік" else "📝"
                meet_link = lesson['conference_link']
                
                lesson_text = (
                    f"  {type_emoji} <b>{lesson['subject']}</b>\n"
                    f"  🕐 {lesson['time']} | 👨‍🏫 {lesson['teacher']}\n"
                    f"  📞 {lesson['teacher_phone']}\n"
                    f"  💻 <a href='{meet_link}'>Google Meet</a> | {exam_emoji} {lesson['exam_type']}"
                )
                message_parts.append(lesson_text)
                # Додаємо розділювач між лекціями (крім останньої)
                if i < len(week_schedule[day]) - 1:
                    message_parts.append("  " + "─" * 15)
            message_parts.append("")
    
    # Створюємо клавіатуру
    if week_type is None:
        keyboard = create_week_keyboard(user_id, current_week)
    else:
        keyboard = create_alternate_week_keyboard(user_id, current_week)
    
    message_text = "\n".join(message_parts)
    
    # Перевіряємо довжину повідомлення
    if len(message_text) > 4000:  # Залишаємо запас для HTML тегів
        # Якщо занадто довге, показуємо тільки заголовки
        short_parts = [f"📆 **Розклад на тиждень** ({week_type_display})", "─" * 40]
        
        for day in days_order:
            if day in week_schedule and week_schedule[day]:
                day_name_ua = schedule._get_day_name_ua(day)
                short_parts.append(f"📅 **{day_name_ua}**")
                
                for i, lesson in enumerate(week_schedule[day]):
                    type_emoji = {"лекція": "📚", "практика": "✏️", "лабораторна": "🔬"}.get(lesson["type"], "📖")
                    short_parts.append(f"  {type_emoji} {lesson['time']} - {lesson['subject']}")
                    # Додаємо розділювач між лекціями (крім останньої)
                    if i < len(week_schedule[day]) - 1:
                        short_parts.append("  " + "─" * 10)
                short_parts.append("")
        
        message_text = "\n".join(short_parts)
        message_text += "\n\n💡 Для деталей використовуйте 'Сьогодні'"
    
    # Перевіряємо чи це callback чи команда
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            logger.log_error(f"Помилка редагування повідомлення: {e}")
            # Якщо не вдалося відредагувати, відправляємо нове
            await update.callback_query.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_text(message_text, parse_mode='HTML', reply_markup=keyboard)


def create_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Створення клавіатури меню залежно від ролі користувача"""
    keyboard = []
    
    if auth_manager.is_user_allowed(user_id):
        # Отримуємо статус оповіщень користувача
        notification_manager = get_notification_manager()
        notifications_enabled = notification_manager.get_user_notifications_status(user_id)
        notification_button_text = "🔔 Увімкнути оповіщення" if not notifications_enabled else "🔕 Вимкнути оповіщення"
        
        # Авторизований користувач
        if user_id == ADMIN_USER_ID:
            # Адміністратор - всі команди
            keyboard.extend([
                [InlineKeyboardButton("📅 Сьогодні", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
                [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
                [InlineKeyboardButton("🔄 Перемкнути тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_switch_week"))],
                [InlineKeyboardButton("📊 Прогрес навчання", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_progress"))],
                [InlineKeyboardButton("📋 Дошка оголошень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_announcements"))],
                [InlineKeyboardButton(notification_button_text, callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_toggle_notifications"))],
                [InlineKeyboardButton("⚙️ Адмін панель", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_admin"))],
                [InlineKeyboardButton("ℹ️ Допомога", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_help"))]
            ])
        else:
            # Звичайний користувач - основні команди
            keyboard.extend([
                [InlineKeyboardButton("📅 Сьогодні", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
                [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
                [InlineKeyboardButton("📊 Прогрес навчання", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_progress"))],
                [InlineKeyboardButton("📋 Дошка оголошень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_announcements"))],
                [InlineKeyboardButton(notification_button_text, callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_toggle_notifications"))],
                [InlineKeyboardButton("ℹ️ Допомога", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_help"))]
            ])
    else:
        # Неавторизований користувач - тільки запит доступу
        keyboard.append([InlineKeyboardButton("🔐 Запросити доступ", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_request_access"))])
    
    return InlineKeyboardMarkup(keyboard)


def create_schedule_keyboard(user_id: int, day: str, week_type: str) -> InlineKeyboardMarkup:
    """Створення клавіатури для розкладу на день"""
    keyboard = [
        [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
        [InlineKeyboardButton("🔄 Перемкнути тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_switch_week"))],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_alternate_schedule_keyboard(user_id: int, day: str, week_type: str) -> InlineKeyboardMarkup:
    """Створення клавіатури для альтернативного розкладу на день"""
    schedule = get_schedule_handler()
    current_week = schedule.get_current_week_type()
    
    # Визначаємо текст кнопки для повернення до поточного типу тижня
    if current_week == "numerator":
        back_to_current_text = "📚 Повернутися до чисельника"
    else:
        back_to_current_text = "📖 Повернутися до знаменника"
    
    keyboard = [
        [InlineKeyboardButton(back_to_current_text, callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
        [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_week_keyboard(user_id: int, week_type: str) -> InlineKeyboardMarkup:
    """Створення клавіатури для розкладу на тиждень"""
    keyboard = [
        [InlineKeyboardButton("🔄 Перемкнути тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_switch_week"))],
        [InlineKeyboardButton("📅 Сьогодні", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_alternate_week_keyboard(user_id: int, week_type: str) -> InlineKeyboardMarkup:
    """Створення клавіатури для альтернативного розкладу на тиждень"""
    schedule = get_schedule_handler()
    current_week = schedule.get_current_week_type()
    
    # Визначаємо текст кнопки для повернення до поточного типу тижня
    if current_week == "numerator":
        back_to_current_text = "📚 Повернутися до чисельника"
    else:
        back_to_current_text = "📖 Повернутися до знаменника"
    
    keyboard = [
        [InlineKeyboardButton(back_to_current_text, callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
        [InlineKeyboardButton("📅 Сьогодні", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_progress_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Створення клавіатури для прогрес-меню"""
    keyboard = [
        [InlineKeyboardButton("📚 Повний графік", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_full_schedule"))],
        [InlineKeyboardButton("🔄 Оновити прогрес", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_progress"))],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_admin_keyboard(admin_user_id: int, users_count: int, pending_count: int) -> InlineKeyboardMarkup:
    """Створення клавіатури для адмін панелі"""
    keyboard = []
    
    if pending_count > 0:
        keyboard.append([InlineKeyboardButton(f"⏳ Схвалити запити ({pending_count})", callback_data=csrf_manager.add_csrf_to_callback_data(admin_user_id, "cmd_pending_requests"))])
    
    if users_count > 0:
        keyboard.append([InlineKeyboardButton(f"👥 Управління користувачами ({users_count})", callback_data=csrf_manager.add_csrf_to_callback_data(admin_user_id, "cmd_manage_users"))])
    
    keyboard.append([InlineKeyboardButton("📋 Управління оголошеннями", callback_data=csrf_manager.add_csrf_to_callback_data(admin_user_id, "cmd_manage_announcements"))])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(admin_user_id, "cmd_menu"))])
    
    return InlineKeyboardMarkup(keyboard)


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """Обробка callback команд меню"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Витягуємо команду з callback даних
    command = data.split("_", 1)[1] if "_" in data else data
    
    if command == "today":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback today")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо розклад на сьогодні
        await show_current_day_schedule(update, context, user_id)
        
    elif command == "week":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback week")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо розклад на тиждень
        await show_week_schedule(update, context, user_id)
        
    elif command == "switch_week":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback switch_week")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо розклад іншого типу тижня (без зміни поточного стану)
        schedule = get_schedule_handler()
        current_week = schedule.get_current_week_type()
        alternate_week = "denominator" if current_week == "numerator" else "numerator"
        
        # Показуємо розклад на поточний день для альтернативного типу тижня
        await show_current_day_schedule_alternate(update, context, user_id, alternate_week)
        
    elif command == "admin":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        # Показуємо адмін панель
        users = auth_manager.get_allowed_users()
        pending_requests = auth_manager.get_pending_requests()
        
        keyboard = create_admin_keyboard(ADMIN_USER_ID, len(users), len(pending_requests))
        
        message_text = (
            f"📋 **Панель адміністратора розкладу**\n\n"
            f"👥 Користувачі з доступом: {len(users)}\n"
            f"⏳ Очікують схвалення: {len(pending_requests)}"
        )
        
        await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
        
    elif command == "help":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback help")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо довідку
        help_text = """
🤖 **Telegram Bot Розкладу Занять - Довідка**

**Основні команди:**
• `/start` - перевірка доступу та початок роботи
• `/schedule` - поточний розклад на сьогодні
• `/today` - розклад на сьогодні
• `/week` - розклад на тиждень
• `/menu` - головне меню
• `/help` - ця довідка

**Для адміністратора:**
• `/admin` - панель управління користувачами

**Як користуватися:**

📅 **Поточний розклад:**
• Натисніть "Сьогодні" щоб побачити розклад на сьогодні
• Поточне заняття виділяється червоним кольором
• Наступне заняття виділяється жовтим кольором
• Таймер показує час до кінця поточної пари

📆 **Розклад на тиждень:**
• Натисніть "Тиждень" щоб побачити весь розклад
• Можна переключатися між чисельником та знаменником
• Кожне заняття має посилання на Google Meet

📊 **Прогрес навчання:**
• Натисніть "Прогрес навчання" для аналізу навчального року
• Візуальні прогрес-бари показують завершення кожного періоду
• Детальний графік навчання з датами та періодами
• Відсотки прогресу розраховуються автоматично

📋 **Дошка оголошень:**
• Натисніть "Дошка оголошень" щоб переглянути актуальні оголошення
• Адміністратор може створювати, редагувати та видаляти оголошення
• При оновленні оголошення всі користувачі отримують сповіщення

🔔 **Сповіщення:**
• Нагадування про заняття за 10 хвилин до початку
• Можна увімкнути/вимкнути в меню
• Сповіщення надсилаються тільки авторизованим користувачам

💻 **Google Meet:**
• Кожне заняття має посилання на Google Meet
• Натисніть "Приєднатися" щоб відкрити конференцію
• Посилання автоматично генеруються з коду заняття

🚨 **Повітряні тривоги:**
• Статус тривог відображається в шапці кожного повідомлення
• Оновлення кожну хвилину для міста Дніпро
• Різні типи тривог: повітряна, артилерійська, міські бої

**Примітки:**
• Розклад автоматично показує поточний тип тижня
• Всі дії логуються для безпеки
• Для доступу потрібне схвалення адміністратора
• Бот працює 24/7 та автоматично оновлює дані
        """
        
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        await safe_edit_message_text(query, help_text, parse_mode='Markdown', reply_markup=back_keyboard)
        
    elif command == "toggle_notifications":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback toggle_notifications")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Перемикаємо статус оповіщень
        notification_manager = get_notification_manager()
        current_status = notification_manager.get_user_notifications_status(user_id)
        new_status = not current_status
        
        if notification_manager.set_user_notifications(user_id, new_status):
            status_text = "увімкнені" if new_status else "вимкнені"
            emoji = "🔔" if new_status else "🔕"
            
            # Створюємо кнопку повернення в меню
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
            ]])
            
            await query.edit_message_text(
                f"{emoji} **Оповіщення {status_text}**\n\n"
                f"Ви {'отримуватимете' if new_status else 'не отримуватимете'} нагадування про заняття за 10 хвилин до початку.",
                reply_markup=back_keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Помилка при зміні налаштувань оповіщень.")
        
    elif command == "progress":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback progress")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо прогрес навчання
        analyzer = ScheduleAnalyzer()
        message_text = analyzer.format_progress_report()
        
        # Створюємо клавіатуру для прогрес-меню
        keyboard = create_progress_keyboard(user_id)
        
        await safe_edit_message_text(query, message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "full_schedule":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback full_schedule")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо повний графік навчання
        analyzer = ScheduleAnalyzer()
        message_text = analyzer.format_full_schedule()
        
        # Перевіряємо довжину повідомлення
        if len(message_text) > 4000:
            # Розбиваємо на частини
            parts = message_text.split('\n')
            current_part = []
            part_length = 0
            part_number = 1
            total_parts = 1
            
            # Спочатку підрахуємо загальну кількість частин
            temp_length = 0
            for line in parts:
                if temp_length + len(line) + 1 > 4000:
                    total_parts += 1
                    temp_length = len(line) + 1
                else:
                    temp_length += len(line) + 1
            
            # Тепер розбиваємо на частини
            for line in parts:
                if part_length + len(line) + 1 > 4000:
                    # Відправляємо поточну частину
                    part_text = '\n'.join(current_part)
                    if part_number == 1:
                        part_text = f"📚 **Повний графік навчання групи KCM-24-11** (частина {part_number}/{total_parts})\n" + part_text
                    else:
                        part_text = f"📚 **Графік навчання** (частина {part_number}/{total_parts})\n" + part_text
                    
                    keyboard = create_progress_keyboard(user_id) if part_number == total_parts else InlineKeyboardMarkup([[
                        InlineKeyboardButton("⏭️ Наступна частина", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_full_schedule_next"))
                    ]])
                    
                    await query.edit_message_text(part_text, parse_mode='Markdown', reply_markup=keyboard)
                    
                    # Очищаємо для наступної частини
                    current_part = [line]
                    part_length = len(line) + 1
                    part_number += 1
                else:
                    current_part.append(line)
                    part_length += len(line) + 1
            
            # Відправляємо останню частину
            if current_part:
                part_text = '\n'.join(current_part)
                if part_number == 1:
                    part_text = f"📚 **Повний графік навчання групи KCM-24-11**\n" + part_text
                else:
                    part_text = f"📚 **Графік навчання** (частина {part_number}/{total_parts})\n" + part_text
                
                keyboard = create_progress_keyboard(user_id)
                await query.edit_message_text(part_text, parse_mode='Markdown', reply_markup=keyboard)
        else:
            keyboard = create_progress_keyboard(user_id)
            await safe_edit_message_text(query, message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "announcements":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback announcements")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо дошку оголошень
        announcement_manager = get_announcement_manager()
        message_text = announcement_manager.format_announcement_message()
        keyboard = announcement_manager.create_announcement_keyboard(user_id, user_id == ADMIN_USER_ID)
        
        await query.edit_message_text(message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "manage_announcements":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        # Показуємо управління оголошеннями для адміна
        announcement_manager = get_announcement_manager()
        message_text = "📋 **Управління оголошеннями**\n\nОберіть дію:"
        keyboard = announcement_manager.create_announcement_management_keyboard(user_id)
        
        await query.edit_message_text(message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "request_access":
        # Запит доступу для неавторизованого користувача
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        await query.edit_message_text(
            "🔐 **Запит на доступ до розкладу**\n\n"
            "Ваш запит на доступ до розкладу занять відправлено адміністратору.\n"
            "Очікуйте схвалення.",
            reply_markup=back_keyboard
        )
        # Відправляємо запит адміну
        await auth_manager.send_access_request_to_admin(update, context, ADMIN_USER_ID)
        
    elif command == "menu":
        # Повернення в головне меню
        keyboard = create_menu_keyboard(user_id)
        
        # Додаємо індикацію повітряної тривоги та типу неділі
        alert_header = await get_air_alert_header()
        
        if auth_manager.is_user_allowed(user_id):
            # Авторизований користувач
            if user_id == ADMIN_USER_ID:
                # Адміністратор
                message_text = alert_header + "👑 Ви адміністратор розкладу"
            else:
                # Звичайний користувач
                message_text = alert_header + "✅ Ви маєте доступ до розкладу занять"
        else:
            # Неавторизований користувач
            message_text = alert_header + "🔐 Для доступу до розкладу потрібна авторизація"
        
        await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='HTML')
        
    elif command == "manage_users":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        # Показуємо список користувачів для управління
        users = auth_manager.get_allowed_users()
        
        if not users:
            # Створюємо кнопку повернення в меню
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
            ]])
            
            await query.edit_message_text("📋 **Панель адміністратора**\n\nНемає користувачів для управління.", reply_markup=back_keyboard)
            return
        
        # Створюємо клавіатуру для управління користувачами
        keyboard = auth_manager.create_users_management_keyboard(users, 0, 10, ADMIN_USER_ID)
        
        message_text = f"📋 **Панель адміністратора**\n\nКористувачі з доступом: {len(users)}\n\nНатисніть на користувача для видалення:"
        
        await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
        
    elif command == "pending_requests":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        # Показуємо запити на доступ
        pending_requests = auth_manager.get_pending_requests()
        
        if not pending_requests:
            # Створюємо кнопку повернення в меню
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
            ]])
            
            await query.edit_message_text("📋 **Панель адміністратора**\n\nНемає запитів на доступ.", reply_markup=back_keyboard)
            return
        
        # Створюємо клавіатуру для схвалення/відхилення запитів
        keyboard = []
        for request in pending_requests:
            username = request.get("username", "без username")
            user_id_req = request.get("user_id", "невідомий")
            timestamp = request.get("timestamp", "невідомий час")
            
            # Обмежуємо довжину username
            display_username = username
            if len(display_username) > 15:
                display_username = display_username[:12] + "..."
            
            keyboard.append([InlineKeyboardButton(
                f"✅ {display_username} ({user_id_req})",
                callback_data=csrf_manager.add_csrf_to_callback_data(user_id, f"approve_{user_id_req}")
            )])
            keyboard.append([InlineKeyboardButton(
                f"❌ Відхилити {display_username}",
                callback_data=csrf_manager.add_csrf_to_callback_data(user_id, f"deny_{user_id_req}")
            )])
        
        # Додаємо кнопку "Назад до меню"
        keyboard.append([InlineKeyboardButton(
            "🔙 Назад до меню",
            callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu")
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"📋 **Запити на доступ**\n\nОчікують схвалення: {len(pending_requests)}\n\nНатисніть для схвалення або відхилення:"
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    else:
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        await query.edit_message_text("❌ Невідома команда.", reply_markup=back_keyboard)


async def handle_announcement_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """Обробка callback команд для оголошень"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Витягуємо команду з callback даних
    command = data.split("_", 1)[1] if "_" in data else data
    
    announcement_manager = get_announcement_manager()
    
    if command == "create":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        # Встановлюємо режим очікування тексту для створення оголошення
        context.user_data['waiting_for_announcement_text'] = True
        context.user_data['announcement_action'] = 'create'
        
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Скасувати", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_cancel"))
        ]])
        
        await query.edit_message_text(
            "✏️ **Створення оголошення**\n\n"
            "Надішліть текст оголошення:",
            parse_mode='Markdown',
            reply_markup=back_keyboard
        )
        
    elif command == "edit":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        current_announcement = announcement_manager.get_current_announcement()
        if not current_announcement:
            await query.edit_message_text("❌ Немає оголошення для редагування.")
            return
        
        # Встановлюємо режим очікування тексту для редагування оголошення
        context.user_data['waiting_for_announcement_text'] = True
        context.user_data['announcement_action'] = 'edit'
        context.user_data['announcement_id'] = current_announcement['id']
        
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Скасувати", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_cancel"))
        ]])
        
        # Екрануємо текст для безпечного відображення
        escaped_content = escape_markdown(current_announcement['content'])
        
        await query.edit_message_text(
            f"✏️ **Редагування оголошення**\n\n"
            f"Поточний текст:\n{escaped_content}\n\n"
            f"Надішліть новий текст:",
            parse_mode='Markdown',
            reply_markup=back_keyboard
        )
        
    elif command == "delete":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        current_announcement = announcement_manager.get_current_announcement()
        if not current_announcement:
            await query.edit_message_text("❌ Немає оголошення для видалення.")
            return
        
        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Так, видалити", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_confirm_delete")),
                InlineKeyboardButton("❌ Скасувати", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "ann_cancel"))
            ]
        ])
        
        # Екрануємо текст для безпечного відображення
        preview_text = current_announcement['content'][:100]
        escaped_preview = escape_markdown(preview_text)
        
        await query.edit_message_text(
            f"🗑️ **Видалення оголошення**\n\n"
            f"Ви впевнені, що хочете видалити це оголошення?\n\n"
            f"Текст: {escaped_preview}{'...' if len(current_announcement['content']) > 100 else ''}",
            parse_mode='Markdown',
            reply_markup=confirm_keyboard
        )
        
    elif command == "confirm_delete":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        current_announcement = announcement_manager.get_current_announcement()
        if not current_announcement:
            await query.edit_message_text("❌ Немає оголошення для видалення.")
            return
        
        announcement_id = current_announcement['id']
        if announcement_manager.delete_announcement(announcement_id):
            logger.log_info(f"Адмін {user_id} видалив оголошення {announcement_id}")
            await query.edit_message_text(
                "✅ **Оголошення видалено**\n\n"
                "Оголошення було успішно видалено.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад до управління", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_manage_announcements"))
                ]])
            )
        else:
            await query.edit_message_text("❌ Помилка при видаленні оголошення.")
            
    elif command == "notify":
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("❌ У вас немає прав адміністратора.")
            return
        
        current_announcement = announcement_manager.get_current_announcement()
        if not current_announcement:
            await query.edit_message_text("❌ Немає оголошення для сповіщення.")
            return
        
        # Отримуємо всіх користувачів
        users = auth_manager.get_allowed_users()
        if not users:
            await query.edit_message_text("❌ Немає користувачів для сповіщення.")
            return
        
        # Відправляємо сповіщення
        sent_count = await announcement_manager.send_notification_to_all_users(context.bot, users)
        
        await query.edit_message_text(
            f"📢 **Сповіщення надіслано**\n\n"
            f"Сповіщення про оновлення оголошення надіслано {sent_count} користувачам.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад до управління", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_manage_announcements"))
            ]])
        )
        
    elif command == "cancel":
        # Скасування операції
        if 'waiting_for_announcement_text' in context.user_data:
            del context.user_data['waiting_for_announcement_text']
        if 'announcement_action' in context.user_data:
            del context.user_data['announcement_action']
        if 'announcement_id' in context.user_data:
            del context.user_data['announcement_id']
        
        # Повертаємося до управління оголошеннями
        message_text = "📋 **Управління оголошеннями**\n\nОберіть дію:"
        keyboard = announcement_manager.create_announcement_management_keyboard(user_id)
        
        await query.edit_message_text(message_text, parse_mode='Markdown', reply_markup=keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка callback запитів"""
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    await query.answer()
    
    # CSRF захист для callback запитів
    if "|csrf:" in data:
        # Витягуємо оригінальні дані з перевіркою CSRF
        original_data = csrf_manager.extract_callback_data(user_id, data)
        if not original_data:
            logger.log_csrf_attack(user_id, data)
            await query.edit_message_text("❌ Невірний токен безпеки. Спробуйте ще раз.")
            return
        data = original_data
    else:
        # Для старих callback без CSRF токенів
        logger.log_csrf_attack(user_id, data)
        await query.edit_message_text("❌ Помилка безпеки. Спробуйте ще раз.")
        return
    
    # Обробка callback для команд меню
    if data.startswith("cmd_"):
        await handle_menu_callback(update, context, data)
        return
    
    # Обробка callback для оголошень
    if data.startswith("ann_"):
        await handle_announcement_callback(update, context, data)
        return
    
    # Обробка callback для адміністратора (схвалення/відхилення користувачів)
    if data.startswith("approve_") or data.startswith("deny_"):
        await auth_manager.handle_admin_callback(update, context)
        return
    
    # Обробка видалення користувача
    if data.startswith("rm_"):
        if user_id != ADMIN_USER_ID:
            logger.log_unauthorized_access_attempt(user_id, "видалення користувача")
            await query.answer("❌ У вас немає прав адміністратора.")
            return
        
        try:
            target_user_id = int(data.split("_", 1)[1])
            
            # Знаходимо username користувача
            username = "невідомий"
            for user in auth_manager.get_allowed_users():
                if user["user_id"] == target_user_id:
                    username = user["username"]
                    break
            
            # Видаляємо користувача
            if auth_manager.revoke_user_access(target_user_id):
                # Логуємо адмін дію
                logger.log_admin_remove_user(user_id, target_user_id, username)
                await query.edit_message_text(f"✅ Користувач @{username} видалено з доступу.")
                
                # Повідомляємо користувача
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="❌ Ваш доступ до бота було відкликано адміністратором."
                    )
                except Exception as e:
                    logger.log_error(f"Помилка відправки повідомлення користувачу: {e}")
            else:
                await query.answer("❌ Помилка при видаленні користувача.")
        except (ValueError, IndexError):
            await query.answer("❌ Невірний ID користувача.")
        return
    
    # Обробка навігації по користувачах
    if data.startswith("up_"):
        if user_id != ADMIN_USER_ID:
            await query.answer("❌ У вас немає прав адміністратора.")
            return
        
        try:
            page = int(data.split("_", 1)[1])
            users = auth_manager.get_allowed_users()
            
            keyboard = auth_manager.create_users_management_keyboard(users, page, 10, ADMIN_USER_ID)
            message_text = f"📋 **Панель адміністратора**\n\nКористувачі з доступом: {len(users)}\n\nНатисніть на користувача для видалення:"
            
            await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
        except (ValueError, IndexError):
            await query.answer("❌ Невірний номер сторінки.")
        return
    
    # Обробка кнопки "Назад до меню"
    if data == "back_to_menu":
        if user_id != ADMIN_USER_ID:
            await query.answer("❌ У вас немає прав адміністратора.")
            return
        
        await query.edit_message_text(
            "📋 **Панель адміністратора**\n\n"
            "Доступні команди:\n"
            "/admin - управління користувачами\n"
            "/search - пошук у базі KeePass\n"
            "/group - пошук за групою\n"
            "/list - показати всі записи"
        )
        return


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка текстових повідомлень"""
    user_id = update.effective_user.id
    
    # Перевіряємо чи користувач очікує введення тексту для оголошення
    if context.user_data.get('waiting_for_announcement_text', False):
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("❌ У вас немає прав адміністратора.")
            return
        
        announcement_text = update.message.text
        announcement_manager = get_announcement_manager()
        username = update.effective_user.username or "без username"
        
        action = context.user_data.get('announcement_action', '')
        
        if action == 'create':
            # Створюємо нове оголошення
            if announcement_manager.create_announcement(announcement_text, user_id, username):
                logger.log_info(f"Адмін {user_id} створив нове оголошення")
                await update.message.reply_text(
                    "✅ **Оголошення створено**\n\n"
                    "Ваше оголошення було успішно створено та опубліковано.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Помилка при створенні оголошення.")
                
        elif action == 'edit':
            # Редагуємо існуюче оголошення
            announcement_id = context.user_data.get('announcement_id')
            if announcement_manager.update_announcement(announcement_id, announcement_text, user_id, username):
                logger.log_info(f"Адмін {user_id} відредагував оголошення {announcement_id}")
                await update.message.reply_text(
                    "✅ **Оголошення оновлено**\n\n"
                    "Ваше оголошення було успішно оновлено.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Помилка при оновленні оголошення.")
        
        # Очищаємо контекст
        context.user_data.pop('waiting_for_announcement_text', None)
        context.user_data.pop('announcement_action', None)
        context.user_data.pop('announcement_id', None)
        
        # Показуємо оновлену дошку оголошень
        message_text = announcement_manager.format_announcement_message()
        keyboard = announcement_manager.create_announcement_management_keyboard(user_id)
        
        await update.message.reply_text(message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    else:
        # Звичайне текстове повідомлення - показуємо меню
        await update.message.reply_text(
            "🤖 Для використання бота скористайтеся командами або меню.\n\n"
            "Натисніть /menu щоб відкрити головне меню.",
            reply_markup=create_menu_keyboard(user_id)
        )


async def safe_edit_message_text(query, text: str, parse_mode: str = None, reply_markup=None) -> bool:
    """
    Безпечне редагування повідомлення з обробкою помилок
    
    Args:
        query: CallbackQuery об'єкт
        text: Текст повідомлення
        parse_mode: Режим парсингу (HTML, Markdown)
        reply_markup: Клавіатура
        
    Returns:
        True якщо редагування успішне, False інакше
    """
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return True
    except Exception as e:
        if "Message is not modified" in str(e):
            # Повідомлення не змінилося, просто відповідаємо
            await query.answer("✅ Дані вже актуальні")
            return True
        else:
            logger.log_error(f"Помилка редагування повідомлення: {e}")
            await query.answer("❌ Помилка оновлення даних")
            return False


def escape_markdown(text: str) -> str:
    """
    Екранування спеціальних символів Markdown
    
    Args:
        text: Текст для екранування
        
    Returns:
        Екранований текст
    """
    if not text:
        return text
    
    # Список символів, які потрібно екранувати в Markdown
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def main() -> None:
    """Головна функція"""
    # Перевіряємо наявність необхідних змінних
    if not TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN not found in config.env")
        return
    
    if not ADMIN_USER_ID:
        print("[ERROR] ADMIN_USER_ID not found in config.env")
        return
    
    print(f"[OK] Configuration checked. Admin ID: {ADMIN_USER_ID}")
    
    # Ініціалізуємо базу даних
    try:
        db = init_database()
        print("[OK] Database initialized")
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        return
    
    # Ініціалізуємо обробник розкладу
    try:
        schedule_handler = init_schedule_handler()
        print("[OK] Schedule handler initialized")
    except Exception as e:
        print(f"[ERROR] Schedule handler initialization failed: {e}")
        return
    
    # Створюємо додаток
    print("[INFO] Creating Telegram application...")
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        print("[OK] Telegram application created")
    except Exception as e:
        print(f"[ERROR] Application creation failed: {e}")
        return
    
    # Додаємо обробники команд
    print("[INFO] Adding command handlers...")
    try:
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("schedule", schedule_command))
        application.add_handler(CommandHandler("today", today_command))
        application.add_handler(CommandHandler("week", week_command))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        print("[OK] Command handlers added")
    except Exception as e:
        print(f"[ERROR] Failed to add handlers: {e}")
        return
    
    # Запускаємо періодичне оновлення статусу тривоги
    print("[INFO] Starting air alert updates...")
    air_alert_manager = get_air_alert_manager()
    print("[OK] Air alert manager ready")
    
    # Запускаємо бота
    print("[INFO] Starting bot...")
    print("[OK] Bot started! Press Ctrl+C to stop")
    
    # Додаємо періодичне оновлення тривоги та оповіщень до додатку
    async def post_init(application):
        """Ініціалізація після запуску бота"""
        air_alert_manager = get_air_alert_manager()
        notification_manager = get_notification_manager()
        
        # Скидаємо історію оповіщень при запуску
        notification_manager.reset_notification_history()
        
        # Запускаємо періодичне оновлення тривоги
        asyncio.create_task(air_alert_manager.start_periodic_update())
        print("[OK] Air alert updates started")
        
        # Запускаємо цикл оповіщень
        asyncio.create_task(notification_manager.start_notification_loop(application.bot))
        print("[OK] Notification loop started")
    
    application.post_init = post_init
    
    try:
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user")
    except Exception as e:
        print(f"[ERROR] Bot startup failed: {e}")
        return


if __name__ == "__main__":
    main()
