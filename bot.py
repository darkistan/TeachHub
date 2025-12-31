#!/usr/bin/env python3
"""
Telegram бот TeachHub для викладачів
Управління розкладом та прогресом навчання
"""
import os
import sys
import asyncio
import logging
from typing import Optional
from dotenv import load_dotenv

# Додаємо поточну директорію в Python path для імпорту модулів
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from auth import auth_manager
from schedule_handler import init_schedule_handler, get_schedule_handler
from logger import logger
from csrf_manager import csrf_manager
from input_validator import input_validator
from air_alert import get_air_alert_manager
from notification_manager import get_notification_manager
from schedule_analyzer import ScheduleAnalyzer
from database import init_database, get_session
from models import ScheduleEntry, PollOption
from poll_manager import get_poll_manager
from datetime import datetime

# Завантажуємо змінні середовища
load_dotenv("config.env")

# Конфігурація
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

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
        
        # Отримуємо ПІБ викладача
        full_name = auth_manager.get_user_full_name(user_id)
        teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
        
        # Всі користувачі Telegram - викладачі
        # Відображаємо ПІБ користувача при старті
        if full_name:
            message_text = alert_header + (
                f"✅ <b>Вітаємо!</b>\n\n"
                f"👤 <b>Ваше ПІБ:</b> {full_name}\n\n"
                f"Ви маєте доступ до розкладу занять"
            )
        else:
            message_text = alert_header + (
                f"✅ <b>Вітаємо, {teacher_display}!</b>\n\n"
                f"Ви маєте доступ до розкладу занять\n\n"
                f"<i>ПІБ не встановлено. Зверніться до адміністратора для призначення ПІБ через веб-інтерфейс.</i>"
            )
        
        await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='HTML')
    else:
        # Неавторизований користувач - можливість запросити доступ
        keyboard = create_menu_keyboard(user_id)
        message_text = alert_header + (
            "🔐 <b>Доступ до розкладу</b>\n\n"
            "Для отримання доступу до розкладу занять натисніть кнопку 'Запросити доступ'.\n"
            "Ваш запит буде відправлено адміністратору через веб-інтерфейс."
        )
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


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда меню з кнопками"""
    user_id = update.effective_user.id
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    # Створюємо клавіатуру залежно від ролі користувача
    keyboard = create_menu_keyboard(user_id)
    
    if auth_manager.is_user_allowed(user_id):
        # Авторизований користувач (викладач)
        # Отримуємо ПІБ викладача
        full_name = auth_manager.get_user_full_name(user_id)
        teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
        
        # Адміністрація тільки через веб-інтерфейс
        # Відображаємо ПІБ користувача в меню
        if full_name:
            message_text = alert_header + (
                f"✅ <b>Вітаємо!</b>\n\n"
                f"👤 <b>Ваше ПІБ:</b> {full_name}\n\n"
                f"Ви маєте доступ до розкладу занять"
            )
        else:
            message_text = alert_header + (
                f"✅ <b>Вітаємо, {teacher_display}!</b>\n\n"
                f"Ви маєте доступ до розкладу занять\n\n"
                f"<i>ПІБ не встановлено. Зверніться до адміністратора для призначення ПІБ через веб-інтерфейс.</i>"
            )
    else:
        # Неавторизований користувач - можливість запросити доступ
        message_text = alert_header + (
            "🔐 <b>Доступ до розкладу</b>\n\n"
            "Для отримання доступу до розкладу занять натисніть кнопку 'Запросити доступ'.\n"
            "Ваш запит буде відправлено адміністратору через веб-інтерфейс."
        )
    
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

<b>Як користуватися:</b>

📅 <b>Поточний розклад:</b>
• Натисніть "Сьогодні" щоб побачити розклад на сьогодні
• Поточне заняття виділяється червоним кольором
• Наступне заняття виділяється жовтим кольором
• Таймер показує час до кінця поточної пари

📆 <b>Розклад на тиждень:</b>
• Натисніть "Тиждень" щоб побачити весь розклад
• Кожне заняття має посилання на Google Meet

📊 <b>Прогрес навчання:</b>
• Натисніть "Прогрес навчання" для аналізу навчального року
• Візуальні прогрес-бари показують завершення кожного періоду
• Детальний графік навчання з датами та періодами
• Відсотки прогресу розраховуються автоматично

📋 <b>Оголошення:</b>
• Оголошення надсилаються адміністратором через веб-інтерфейс прямо в чат
• Ви отримуєте оголошення автоматично в Telegram

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
    """Показ розкладу на поточний день для альтернативного типу тижня (для викладача)"""
    schedule = get_schedule_handler()
    current_day_name = schedule.get_current_day_name()
    
    # Отримуємо ПІБ викладача
    full_name = auth_manager.get_user_full_name(user_id)
    teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
    
    # Отримуємо розклад для альтернативного типу тижня для цього викладача
    lessons = schedule.get_day_schedule(current_day_name, week_type, teacher_user_id=user_id)
    
    # Формуємо повідомлення
    day_name_ua = schedule._get_day_name_ua(current_day_name)
    week_type_display = "📖 Тиждень знаменника" if week_type == "denominator" else "📚 Тиждень чисельника"
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📅 <b>{day_name_ua}</b> ({week_type_display})",
        f"👨‍🏫 <b>{teacher_display}</b>",
        "─" * 30
    ]
    
    if lessons:
        message_parts.append("📚 <b>Заняття на день:</b>")
        message_parts.append("")
        for i, lesson in enumerate(lessons):
            message_parts.append(schedule.format_lesson_for_display(lesson, is_current=False))
            # Додаємо розділювач між лекціями (крім останньої)
            if i < len(lessons) - 1:
                message_parts.append("─" * 20)
    else:
        message_parts.append("📚 <b>Занять на цей день немає</b>")
    
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
    """Показ розкладу на поточний день для викладача"""
    schedule = get_schedule_handler()
    current_day_name = schedule.get_current_day_name()
    current_week = schedule.get_current_week_type()
    
    # Отримуємо інформацію про поточне та наступне заняття для цього викладача
    current_lesson, next_lesson = schedule.get_current_lesson_info(teacher_user_id=user_id)
    
    # Отримуємо ПІБ викладача
    full_name = auth_manager.get_user_full_name(user_id)
    teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
    
    # Формуємо повідомлення
    day_name_ua = schedule._get_day_name_ua(current_day_name)
    week_type_display = schedule.get_week_type_display()
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📅 <b>{day_name_ua}</b> ({week_type_display})",
        f"👨‍🏫 <b>{teacher_display}</b>",
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
        message_parts.append("🟢 <b>Поточних занять немає</b>")
        message_parts.append("")
    
    # Показуємо наступне заняття
    if next_lesson:
        message_parts.append(schedule.format_lesson_for_display(next_lesson, is_current=False))
    else:
        # Показуємо всі заняття на день якщо немає наступного
        lessons = schedule.get_day_schedule(current_day_name, current_week, teacher_user_id=user_id)
        if lessons:
            message_parts.append("📚 <b>Всі заняття на день:</b>")
            message_parts.append("")
            
            # Сортуємо заняття по часу
            sorted_lessons = sorted(lessons, key=lambda x: x['time'])
            
            for i, lesson in enumerate(sorted_lessons):
                message_parts.append(schedule.format_lesson_for_display(lesson, is_current=False))
                
                # Перевіряємо великі вікна між заняттями (>15 хв)
                # НЕ враховуємо час до початку першої пари та після останньої
                if i < len(sorted_lessons) - 1:
                    current_end = lesson['time'].split('-')[1] if '-' in lesson['time'] else None
                    next_start = sorted_lessons[i + 1]['time'].split('-')[0] if '-' in sorted_lessons[i + 1]['time'] else None
                    
                    if current_end and next_start:
                        try:
                            end_time = datetime.strptime(current_end, "%H:%M")
                            start_time = datetime.strptime(next_start, "%H:%M")
                            gap_minutes = (start_time - end_time).total_seconds() / 60
                            
                            # Показуємо тільки вікна більше 15 хвилин між заняттями
                            if gap_minutes > 15:
                                hours = int(gap_minutes // 60)
                                minutes = int(gap_minutes % 60)
                                if hours > 0:
                                    gap_text = f"{hours}г {minutes}хв"
                                else:
                                    gap_text = f"{minutes}хв"
                                message_parts.append("")
                                message_parts.append(f"⏸️ <b>Вікно:</b> {gap_text}")
                                message_parts.append("")
                        except (ValueError, IndexError):
                            pass
                    
                    # Додаємо розділювач між лекціями (крім останньої)
                    if i < len(sorted_lessons) - 1:
                        message_parts.append("─" * 20)
        else:
            message_parts.append("📚 <b>Занять на сьогодні немає</b>")
    
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


async def show_teacher_workload_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Показ статистики навантаження викладача"""
    try:
        with get_session() as session:
            # Отримуємо всі заняття викладача
            entries = session.query(ScheduleEntry).filter(
                ScheduleEntry.teacher_user_id == user_id
            ).all()
            
            # Розраховуємо години
            total_hours = 0
            by_day = {}
            by_type = {}
            lessons_count = 0
            
            for entry in entries:
                # Парсимо час (наприклад, "08:30-09:50")
                try:
                    time_str = entry.time
                    if '-' in time_str:
                        start_str, end_str = time_str.split('-')
                        start = datetime.strptime(start_str, "%H:%M")
                        end = datetime.strptime(end_str, "%H:%M")
                        duration = (end - start).total_seconds() / 3600  # Години
                        total_hours += duration
                        lessons_count += 1
                        
                        # По днях
                        day = entry.day_of_week
                        by_day[day] = by_day.get(day, 0) + duration
                        
                        # По типах заняття
                        lesson_type = entry.lesson_type
                        by_type[lesson_type] = by_type.get(lesson_type, 0) + duration
                except (ValueError, AttributeError):
                    continue
            
            # Отримуємо ПІБ викладача
            full_name = auth_manager.get_user_full_name(user_id)
            teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
            
            # Формуємо повідомлення
            day_names_ua = {
                'monday': 'Понеділок', 'tuesday': 'Вівторок', 'wednesday': 'Середа',
                'thursday': 'Четвер', 'friday': "П'ятниця", 'saturday': 'Субота', 'sunday': 'Неділя'
            }
            
            message_parts = [
                f"📈 <b>Статистика навантаження</b>",
                f"👨‍🏫 <b>{teacher_display}</b>",
                "─" * 30,
                f"⏰ <b>Загальне навантаження:</b> {total_hours:.1f} год/тиждень",
                f"📚 <b>Кількість занять:</b> {lessons_count}",
                ""
            ]
            
            # По днях
            if by_day:
                message_parts.append("<b>📅 По днях тижня:</b>")
                days_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                for day in days_order:
                    if day in by_day:
                        day_name = day_names_ua.get(day, day)
                        hours = by_day[day]
                        message_parts.append(f"  {day_name}: {hours:.1f} год")
                message_parts.append("")
            
            # По типах заняття
            if by_type:
                message_parts.append("<b>📖 По типах заняття:</b>")
                for lesson_type, hours in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                    message_parts.append(f"  {lesson_type}: {hours:.1f} год")
            
            message_text = "\n".join(message_parts)
            
            # Створюємо клавіатуру
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
            ]])
            
            query = update.callback_query
            if query:
                await safe_edit_message_text(query, message_text, parse_mode='HTML', reply_markup=back_keyboard)
            else:
                await update.message.reply_text(message_text, parse_mode='HTML', reply_markup=back_keyboard)
                
    except Exception as e:
        logger.log_error(f"Помилка показу статистики навантаження: {e}")
        error_text = "❌ Помилка завантаження статистики навантаження."
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        query = update.callback_query
        if query:
            await safe_edit_message_text(query, error_text, parse_mode='HTML', reply_markup=back_keyboard)
        else:
            await update.message.reply_text(error_text, parse_mode='HTML', reply_markup=back_keyboard)


async def show_week_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, week_type: Optional[str] = None) -> None:
    """Показ розкладу на тиждень для викладача"""
    schedule = get_schedule_handler()
    if week_type is None:
        current_week = schedule.get_current_week_type()
    else:
        current_week = week_type
    
    week_type_display = "📖 Тиждень знаменника" if current_week == "denominator" else "📚 Тиждень чисельника"
    
    # Отримуємо ПІБ викладача
    full_name = auth_manager.get_user_full_name(user_id)
    teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
    
    # Отримуємо розклад на тиждень для цього викладача
    week_schedule = schedule.get_week_schedule(current_week, teacher_user_id=user_id)
    
    # Додаємо індикацію повітряної тривоги
    alert_header = await get_air_alert_header()
    
    message_parts = [
        alert_header,
        f"📆 <b>Розклад на тиждень</b> ({week_type_display})",
        f"👨‍🏫 <b>{teacher_display}</b>",
        "─" * 40
    ]
    
    days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    for day in days_order:
        if day in week_schedule and week_schedule[day]:
            day_name_ua = schedule._get_day_name_ua(day)
            message_parts.append(f"📅 <b>{day_name_ua}</b>")
            
            for i, lesson in enumerate(week_schedule[day]):
                # Показуємо тільки основну інформацію для розкладу на тиждень
                type_emoji = {"лекція": "📚", "практика": "✏️", "лабораторна": "🔬"}.get(lesson["type"], "📖")
                exam_emoji = "✅" if lesson["exam_type"] == "залік" else "📝"
                meet_link = lesson['conference_link']
                
                # Показуємо групу замість викладача
                group_info = lesson.get('group_name', 'не вказана')
                headman_info = ""
                if lesson.get('headman_name') or lesson.get('headman_phone'):
                    headman_parts = []
                    if lesson.get('headman_name'):
                        headman_parts.append(lesson['headman_name'])
                    if lesson.get('headman_phone'):
                        headman_parts.append(lesson['headman_phone'])
                    if headman_parts:
                        headman_info = f"\n  👤 Староста: {' | '.join(headman_parts)}"
                
                lesson_text = (
                    f"  {type_emoji} <b>{lesson['subject']}</b>\n"
                    f"  🕐 {lesson['time']} | 👥 Група: {group_info}{headman_info}\n"
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
        short_parts = [f"📆 <b>Розклад на тиждень</b> ({week_type_display})", "─" * 40]
        
        for day in days_order:
            if day in week_schedule and week_schedule[day]:
                day_name_ua = schedule._get_day_name_ua(day)
                short_parts.append(f"📅 <b>{day_name_ua}</b>")
                
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
        # Отримуємо роль користувача
        user_role = auth_manager.get_user_role(user_id) or 'user'
        
        # Отримуємо статус оповіщень користувача
        notification_manager = get_notification_manager()
        notifications_enabled = notification_manager.get_user_notifications_status(user_id)
        notification_button_text = "🔔 Увімкнути оповіщення" if not notifications_enabled else "🔕 Вимкнути оповіщення"
        
        # Всі викладачі мають однакове меню (прибрано адмін-панель та дошку оголошень)
        keyboard.extend([
            [InlineKeyboardButton("📅 Сьогодні", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_today"))],
            [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
            [InlineKeyboardButton("📊 Прогрес навчання", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_progress"))],
            [InlineKeyboardButton("📈 Статистика", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_stats"))],
            [InlineKeyboardButton(notification_button_text, callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_toggle_notifications"))],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_help"))]
        ])
    else:
        # Неавторизований користувач - можливість запросити доступ
        keyboard.append([InlineKeyboardButton("🔐 Запросити доступ", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_request_access"))])
    
    return InlineKeyboardMarkup(keyboard)


def create_schedule_keyboard(user_id: int, day: str, week_type: str) -> InlineKeyboardMarkup:
    """Створення клавіатури для розкладу на день"""
    keyboard = [
        [InlineKeyboardButton("📆 Тиждень", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_week"))],
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
        [InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))]
    ]
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
        
    elif command == "help":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback help")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо довідку
        help_text = """
🤖 <b>Telegram Bot Розкладу Занять - Довідка</b>

<b>Основні команди:</b>
• `/start` - перевірка доступу та початок роботи
• `/schedule` - поточний розклад на сьогодні
• `/today` - розклад на сьогодні
• `/week` - розклад на тиждень
• `/menu` - головне меню
• `/help` - ця довідка

<b>Як користуватися:</b>

📅 <b>Поточний розклад:</b>
• Натисніть "Сьогодні" щоб побачити розклад на сьогодні
• Поточне заняття виділяється червоним кольором
• Наступне заняття виділяється жовтим кольором
• Таймер показує час до кінця поточної пари

📆 <b>Розклад на тиждень:</b>
• Натисніть "Тиждень" щоб побачити весь розклад
• Кожне заняття має посилання на Google Meet

📊 <b>Прогрес навчання:</b>
• Натисніть "Прогрес навчання" для аналізу навчального року
• Візуальні прогрес-бари показують завершення кожного періоду
• Детальний графік навчання з датами та періодами
• Відсотки прогресу розраховуються автоматично

📋 <b>Оголошення:</b>
• Оголошення надсилаються адміністратором через веб-інтерфейс прямо в чат
• Ви отримуєте оголошення автоматично в Telegram

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
        
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        await safe_edit_message_text(query, help_text, parse_mode='HTML', reply_markup=back_keyboard)
        
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
            
            # Отримуємо ПІБ викладача для відображення
            full_name = auth_manager.get_user_full_name(user_id)
            teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
            
            message = f"{emoji} <b>Оповіщення {status_text}</b>\n\n"
            if full_name:
                message += f"👤 <b>Ваше ПІБ:</b> {full_name}\n\n"
            message += f"Ви {'отримуватимете' if new_status else 'не отримуватимете'} нагадування про заняття за 10 хвилин до початку."
            
            await query.edit_message_text(
                message,
                reply_markup=back_keyboard,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("❌ Помилка при зміні налаштувань оповіщень.")
        
    elif command == "current_lesson":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback current_lesson")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо поточне заняття з таймером
        await show_current_lesson_for_parent(update, context, user_id)
        
    elif command == "stats":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback stats")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо статистику навантаження викладача
        await show_teacher_workload_stats(update, context, user_id)
        
    elif command == "progress":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback progress")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Отримуємо ПІБ викладача
        full_name = auth_manager.get_user_full_name(user_id)
        teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
        
        # Показуємо прогрес навчання для цього викладача
        analyzer = ScheduleAnalyzer()
        message_text = analyzer.format_progress_report(teacher_user_id=user_id)
        
        # Додаємо інформацію про викладача
        message_text = f"👨‍🏫 <b>{teacher_display}</b>\n\n" + message_text
        
        # Створюємо клавіатуру для прогрес-меню
        keyboard = create_progress_keyboard(user_id)
        
        await safe_edit_message_text(query, message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "full_schedule":
        if not auth_manager.is_user_allowed(user_id):
            logger.log_unauthorized_access_attempt(user_id, "menu callback full_schedule")
            await query.edit_message_text("❌ У вас немає доступу до розкладу.")
            return
        
        # Показуємо повний графік навчання для цього викладача
        analyzer = ScheduleAnalyzer()
        message_text = analyzer.format_full_schedule(teacher_user_id=user_id)
        
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
                        part_text = f"📚 <b>Повний графік навчання групи KCM-24-11</b> (частина {part_number}/{total_parts})\n" + part_text
                    else:
                        part_text = f"📚 <b>Графік навчання</b> (частина {part_number}/{total_parts})\n" + part_text
                    
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
                    part_text = f"📚 <b>Повний графік навчання групи KCM-24-11</b>\n" + part_text
                else:
                    part_text = f"📚 <b>Графік навчання</b> (частина {part_number}/{total_parts})\n" + part_text
                
                keyboard = create_progress_keyboard(user_id)
                await query.edit_message_text(part_text, parse_mode='Markdown', reply_markup=keyboard)
        else:
            keyboard = create_progress_keyboard(user_id)
            await safe_edit_message_text(query, message_text, parse_mode='Markdown', reply_markup=keyboard)
        
    elif command == "request_access":
        # Запит доступу - створюємо запис в PendingRequest для веб-інтерфейсу
        user = update.effective_user
        username = user.username or f"user_{user.id}"
        
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        # Додаємо запит в БД
        if auth_manager.add_user_request(user_id, username):
            await query.edit_message_text(
                "🔐 <b>Запит на доступ відправлено</b>\n\n"
                "Ваш запит на доступ до розкладу занять відправлено адміністратору.\n"
                "Адміністратор перегляне ваш запит через веб-інтерфейс та надасть доступ.\n\n"
                "Очікуйте схвалення.",
                reply_markup=back_keyboard,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                "ℹ️ <b>Запит вже відправлено</b>\n\n"
                "Ви вже надіслали запит на доступ.\n"
                "Адміністратор перегляне його через веб-інтерфейс та надасть доступ.\n\n"
                "Очікуйте схвалення.",
                reply_markup=back_keyboard,
                parse_mode='HTML'
            )
        
    elif command == "menu":
        # Повернення в головне меню
        keyboard = create_menu_keyboard(user_id)
        
        # Отримуємо ПІБ викладача для відображення
        full_name = auth_manager.get_user_full_name(user_id)
        teacher_display = full_name if full_name else (update.effective_user.username or "Викладач")
        
        # Додаємо індикацію повітряної тривоги та типу неділі
        alert_header = await get_air_alert_header()
        
        if auth_manager.is_user_allowed(user_id):
            # Авторизований користувач (викладач)
            # ПІБ вже отримано вище
            if full_name:
                message_text = alert_header + (
                    f"✅ <b>Вітаємо!</b>\n\n"
                    f"👤 <b>Ваше ПІБ:</b> {full_name}\n\n"
                    f"Ви маєте доступ до розкладу занять"
                )
            else:
                message_text = alert_header + (
                    f"✅ <b>Вітаємо, {teacher_display}!</b>\n\n"
                    f"Ви маєте доступ до розкладу занять\n\n"
                    f"<i>ПІБ не встановлено. Зверніться до адміністратора для призначення ПІБ через веб-інтерфейс.</i>"
                )
        else:
            # Неавторизований користувач - можливість запросити доступ
            message_text = alert_header + (
                "🔐 <b>Доступ до розкладу</b>\n\n"
                "Для отримання доступу до розкладу занять натисніть кнопку 'Запросити доступ'.\n"
                "Ваш запит буде відправлено адміністратору через веб-інтерфейс."
            )
        
        await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='HTML')
        
    else:
        # Створюємо кнопку повернення в меню
        back_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад в меню", callback_data=csrf_manager.add_csrf_to_callback_data(user_id, "cmd_menu"))
        ]])
        
        await query.edit_message_text("❌ Невідома команда.", reply_markup=back_keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка callback запитів"""
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    await query.answer()
    
    # Обробка голосування в опитуванні (без CSRF, оскільки це не команди меню)
    if data.startswith("poll_vote_"):
        if not auth_manager.is_user_allowed(user_id):
            await query.answer("❌ У вас немає доступу до цієї функції.", show_alert=True)
            return
        
        # Витягуємо poll_id та option_id з callback_data
        # Формат: poll_vote_{poll_id}_{option_id}
        parts = data.split("_")
        if len(parts) >= 4:
            try:
                poll_id = int(parts[2])
                option_id = int(parts[3])
                
                poll_manager = get_poll_manager()
                
                if poll_manager.add_poll_response(poll_id, option_id, user_id):
                    # Показуємо помітне підтвердження
                    await query.answer("✅ Ваш голос зараховано!", show_alert=True)
                    
                    # Оновлюємо кнопки, щоб показати обрану відповідь
                    try:
                        with get_session() as session:
                            # Отримуємо всі варіанти відповіді для цього опитування
                            options = session.query(PollOption).filter(
                                PollOption.poll_id == poll_id
                            ).order_by(PollOption.option_order).all()
                            
                            # Створюємо нові кнопки з позначкою обраної відповіді
                            keyboard_buttons = []
                            for option in options:
                                if option.id == option_id:
                                    # Обрана відповідь - показуємо помітну позначку
                                    button_text = f"✅ ✓ {option.option_text} ✓ (Відправлено)"
                                else:
                                    # Інші відповіді - залишаємо як є, але можна додати індикацію
                                    button_text = f"✅ {option.option_text}"
                                
                                # Кнопки залишаються активними (користувач може змінити вибір)
                                keyboard_buttons.append([{
                                    'text': button_text,
                                    'callback_data': f"poll_vote_{poll_id}_{option.id}"
                                }])
                            
                            # Оновлюємо повідомлення з новими кнопками
                            # Отримуємо оригінальний текст (може бути text або caption для медіа)
                            original_text = query.message.text or query.message.caption or ""
                            
                            # Додаємо помітне підтвердження до тексту
                            # Перевіряємо, чи вже є підтвердження в тексті
                            if "✅ Ваш голос зараховано" not in original_text:
                                confirmation_text = "\n\n━━━━━━━━━━━━━━━━━━━━\n✅ <b>ВАШ ГОЛОС ЗАРАХОВАНО!</b> ✅\n━━━━━━━━━━━━━━━━━━━━"
                                new_text = original_text + confirmation_text
                            else:
                                new_text = original_text
                            
                            await query.edit_message_text(
                                new_text,
                                parse_mode='HTML',
                                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
                            )
                            
                    except Exception as e:
                        logger.log_warning(f"Не вдалося оновити повідомлення з опитуванням: {e}")
                        # Якщо не вдалося оновити, хоча б показуємо alert
                else:
                    await query.answer("❌ Помилка збереження голосу. Можливо, опитування вже закрите.", show_alert=True)
            except (ValueError, IndexError) as e:
                logger.log_error(f"Помилка парсингу callback_data для голосування: {e}")
                await query.answer("❌ Помилка обробки голосу", show_alert=True)
        else:
            await query.answer("❌ Невірний формат команди", show_alert=True)
        return
    
    # CSRF захист для callback запитів (тільки для команд меню)
    if "|csrf:" in data:
        # Витягуємо оригінальні дані з перевіркою CSRF
        original_data = csrf_manager.extract_callback_data(user_id, data)
        if not original_data:
            # Перевіряємо чи користувач є в базі даних
            if auth_manager.is_user_allowed(user_id):
                # Користувач проекту - токен прострочений
                logger.log_csrf_expired_token(user_id, data)
            else:
                # Користувача немає в базі - можлива атака
                logger.log_csrf_attack(user_id, data)
            await query.edit_message_text("❌ Невірний токен безпеки. Спробуйте ще раз.")
            return
        data = original_data
    else:
        # Для старих callback без CSRF токенів (тільки команди меню)
        # Перевіряємо чи користувач є в базі даних
        if auth_manager.is_user_allowed(user_id):
            # Користувач проекту - токен прострочений
            logger.log_csrf_expired_token(user_id, data)
        else:
            # Користувача немає в базі - можлива атака
            logger.log_csrf_attack(user_id, data)
        await query.edit_message_text("❌ Помилка безпеки. Спробуйте ще раз.")
        return
    
    # Обробка callback для команд меню
    if data.startswith("cmd_"):
        await handle_menu_callback(update, context, data)
        return
    
    # Всі інші callback - невідома команда
    await query.answer("❌ Невідома команда.")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка текстових повідомлень"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Перевіряємо чи користувач авторизований
    if not auth_manager.is_user_allowed(user_id):
        logger.log_unauthorized_access_attempt(user_id, "text message")
        await update.message.reply_text("❌ У вас немає доступу до розкладу.")
        return
    
    # Звичайне текстове повідомлення - показуємо меню
    await update.message.reply_text(
        "🤖 Для використання бота скористайтеся командами або меню.\n\n"
        "Натисніть /menu щоб відкрити головне меню.",
        reply_markup=create_menu_keyboard(user_id)
    )


async def safe_send_html_message(update_or_query, text: str, reply_markup=None, is_edit: bool = False) -> bool:
    """
    Безпечна відправка/редагування HTML повідомлення з обробкою помилок парсингу
    
    Args:
        update_or_query: Update або CallbackQuery об'єкт
        text: Текст повідомлення з HTML розміткою
        reply_markup: Клавіатура
        is_edit: True якщо редагування, False якщо нова відправка
        
    Returns:
        True якщо успішно, False інакше
    """
    import re
    
    try:
        if is_edit:
            # Редагування повідомлення
            if hasattr(update_or_query, 'edit_message_text'):
                await update_or_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update_or_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            # Нова відправка
            if hasattr(update_or_query, 'reply_text'):
                await update_or_query.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
            elif hasattr(update_or_query, 'message') and hasattr(update_or_query.message, 'reply_text'):
                await update_or_query.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update_or_query.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
        return True
    except Exception as e:
        error_str = str(e).lower()
        if "parse entities" in error_str or "can't parse" in error_str or "can't find end" in error_str:
            # Помилка парсингу HTML - видаляємо HTML теги та екрануємо
            logger.log_warning(f"Помилка парсингу HTML, використовуємо plain text: {e}")
            clean_text = re.sub(r'<[^>]+>', '', text)
            # Екрануємо залишкові спеціальні символи
            clean_text = clean_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            clean_text = clean_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            try:
                if is_edit:
                    if hasattr(update_or_query, 'edit_message_text'):
                        await update_or_query.edit_message_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                    else:
                        await update_or_query.edit_message_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                else:
                    if hasattr(update_or_query, 'reply_text'):
                        await update_or_query.reply_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                    elif hasattr(update_or_query, 'message') and hasattr(update_or_query.message, 'reply_text'):
                        await update_or_query.message.reply_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                    else:
                        await update_or_query.reply_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                return True
            except Exception as e2:
                logger.log_error(f"Помилка відправки plain text повідомлення: {e2}")
                return False
        else:
            # Інша помилка
            if "message is not modified" in error_str:
                if hasattr(update_or_query, 'answer'):
                    await update_or_query.answer("✅ Дані вже актуальні")
                return True
            logger.log_error(f"Помилка відправки/редагування повідомлення: {e}")
            return False


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
        error_str = str(e)
        
        if "Message is not modified" in error_str:
            # Повідомлення не змінилося, просто відповідаємо
            await query.answer("✅ Дані вже актуальні")
            return True
        elif "parse entities" in error_str.lower() or "can't parse" in error_str.lower() or "can't find end" in error_str.lower():
            # Помилка парсингу HTML/Markdown - спробуємо без parse_mode
            logger.log_warning(f"Помилка парсингу {parse_mode}, спроба без форматування: {e}")
            try:
                # Видаляємо HTML теги та екрануємо спеціальні символи
                import re
                # Видаляємо HTML теги
                clean_text = re.sub(r'<[^>]+>', '', text)
                # Відновлюємо та екрануємо спеціальні символи правильно
                clean_text = clean_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                clean_text = clean_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                await query.edit_message_text(clean_text, parse_mode=None, reply_markup=reply_markup)
                return True
            except Exception as e2:
                logger.log_error(f"Помилка редагування повідомлення (fallback): {e2}")
                await query.answer("❌ Помилка оновлення даних")
                return False
        else:
            logger.log_error(f"Помилка редагування повідомлення: {e}")
            await query.answer("❌ Помилка оновлення даних")
            return False


def escape_html(text: str) -> str:
    """
    Екранування спеціальних символів HTML для Telegram Bot API
    
    Args:
        text: Текст для екранування
        
    Returns:
        Екранований текст
    """
    if not text:
        return text
    
    # Екранування HTML символів
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    return text


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
    
    print("[OK] Configuration checked")
    
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
        
        # Запускаємо перевірку термінів дії опитувань
        async def check_expired_polls():
            """Періодична перевірка та закриття опитувань з закінченим терміном"""
            from poll_manager import get_poll_manager
            poll_manager = get_poll_manager()
            
            while True:
                try:
                    await asyncio.sleep(300)  # Перевіряємо кожні 5 хвилин
                    closed_count = poll_manager.check_and_close_expired_polls()
                    if closed_count > 0:
                        logger.log_info(f"Автоматично закрито {closed_count} опитувань з закінченим терміном")
                except Exception as e:
                    logger.log_error(f"Помилка перевірки термінів опитувань: {e}")
        
        asyncio.create_task(check_expired_polls())
        print("[OK] Expired polls checker started")
        
        # Запускаємо перевірку термінів дії опитувань
        async def check_expired_polls():
            """Періодична перевірка та закриття опитувань з закінченим терміном"""
            from poll_manager import get_poll_manager
            import asyncio
            poll_manager = get_poll_manager()
            
            while True:
                try:
                    await asyncio.sleep(300)  # Перевіряємо кожні 5 хвилин
                    closed_count = poll_manager.check_and_close_expired_polls()
                    if closed_count > 0:
                        logger.log_info(f"Автоматично закрито {closed_count} опитувань з закінченим терміном")
                except Exception as e:
                    logger.log_error(f"Помилка перевірки термінів опитувань: {e}")
        
        asyncio.create_task(check_expired_polls())
        print("[OK] Expired polls checker started")
        
        # Запускаємо перевірку термінів дії опитувань
        async def check_expired_polls():
            """Періодична перевірка та закриття опитувань з закінченим терміном"""
            from poll_manager import get_poll_manager
            import asyncio
            poll_manager = get_poll_manager()
            
            while True:
                try:
                    await asyncio.sleep(300)  # Перевіряємо кожні 5 хвилин
                    closed_count = poll_manager.check_and_close_expired_polls()
                    if closed_count > 0:
                        logger.log_info(f"Автоматично закрито {closed_count} опитувань з закінченим терміном")
                except Exception as e:
                    logger.log_error(f"Помилка перевірки термінів опитувань: {e}")
        
        asyncio.create_task(check_expired_polls())
        print("[OK] Expired polls checker started")
    
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
