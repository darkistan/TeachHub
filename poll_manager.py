"""
Модуль для управління опитуваннями
Створення опитувань викладачами через Telegram та опрацювання результатів адміном
"""
import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from database import get_session
from models import Poll, PollOption, PollResponse, User
from logger import logger

# Завантажуємо змінні середовища
load_dotenv("config.env")

# Telegram Bot API URL
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


class PollManager:
    """Клас для управління опитуваннями"""
    
    def __init__(self):
        """Ініціалізація менеджера опитувань"""
        pass
    
    def create_poll(
        self,
        question: str,
        options: List[str],
        author_id: int,
        author_username: str,
        expires_at: Optional[datetime] = None,
        is_anonymous: bool = False
    ) -> Optional[int]:
        """
        Створення нового опитування
        
        Args:
            question: Питання опитування
            options: Список варіантів відповіді (мінімум 2, максимум 10)
            author_id: ID автора (викладача)
            author_username: Username автора
            
        Returns:
            ID створеного опитування або None при помилці
        """
        try:
            if len(options) < 2:
                logger.log_error("Опитування має містити мінімум 2 варіанти відповіді")
                return None
            
            if len(options) > 10:
                logger.log_error("Опитування має містити максимум 10 варіантів відповіді")
                return None
            
            with get_session() as session:
                # Створюємо опитування
                poll = Poll(
                    question=question,
                    author_id=author_id,
                    author_username=author_username,
                    is_closed=False,
                    report_sent=False,
                    expires_at=expires_at,
                    sent_to_users=False,
                    is_anonymous=is_anonymous
                )
                session.add(poll)
                session.flush()  # Отримуємо ID опитування
                
                # Додаємо варіанти відповіді
                for order, option_text in enumerate(options, start=1):
                    option = PollOption(
                        poll_id=poll.id,
                        option_text=option_text.strip(),
                        option_order=order
                    )
                    session.add(option)
                
                session.commit()
                logger.log_info(f"Створено опитування ID {poll.id} від користувача {author_id}")
                return poll.id
        except Exception as e:
            logger.log_error(f"Помилка створення опитування: {e}")
            return None
    
    def update_poll(
        self,
        poll_id: int,
        question: str,
        options: List[str],
        expires_at: Optional[datetime] = None,
        is_anonymous: bool = False
    ) -> bool:
        """
        Оновлення опитування (тільки якщо воно ще не відправлено користувачам)
        
        Args:
            poll_id: ID опитування
            question: Питання опитування
            options: Список варіантів відповіді (мінімум 2, максимум 10)
            expires_at: Термін дії опитування
            is_anonymous: Чи є опитування анонімним
            
        Returns:
            True якщо опитування успішно оновлено
        """
        try:
            if len(options) < 2:
                logger.log_error("Опитування має містити мінімум 2 варіанти відповіді")
                return False
            
            if len(options) > 10:
                logger.log_error("Опитування має містити максимум 10 варіантів відповіді")
                return False
            
            with get_session() as session:
                # Перевіряємо чи опитування існує
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.log_error(f"Опитування {poll_id} не знайдено")
                    return False
                
                # Перевіряємо чи опитування вже відправлено
                if poll.sent_to_users:
                    logger.log_error(f"Опитування {poll_id} вже відправлено користувачам, редагування неможливе")
                    return False
                
                # Перевіряємо чи опитування не закрите
                if poll.is_closed:
                    logger.log_error(f"Опитування {poll_id} вже закрите, редагування неможливе")
                    return False
                
                # Оновлюємо питання
                poll.question = question
                poll.expires_at = expires_at
                poll.is_anonymous = is_anonymous
                
                # Видаляємо старі варіанти відповіді
                session.query(PollOption).filter(PollOption.poll_id == poll_id).delete()
                
                # Додаємо нові варіанти відповіді
                for order, option_text in enumerate(options, start=1):
                    option = PollOption(
                        poll_id=poll.id,
                        option_text=option_text.strip(),
                        option_order=order
                    )
                    session.add(option)
                
                session.commit()
                logger.log_info(f"Опитування ID {poll_id} оновлено")
                return True
        except Exception as e:
            logger.log_error(f"Помилка оновлення опитування: {e}")
            return False
    
    def get_active_polls(self) -> List[Dict[str, Any]]:
        """
        Отримання списку активних (незакритих) опитувань
        
        Returns:
            Список активних опитувань з інформацією про автора та кількість відповідей
        """
        try:
            with get_session() as session:
                polls = session.query(Poll).filter(
                    Poll.is_closed == False
                ).order_by(Poll.created_at.desc()).all()
                
                result = []
                for poll in polls:
                    # Отримуємо автора
                    author = session.query(User).filter(User.user_id == poll.author_id).first()
                    author_name = author.full_name if author and author.full_name else poll.author_username or f"ID: {poll.author_id}"
                    
                    # Отримуємо кількість відповідей
                    response_count = session.query(PollResponse).filter(
                        PollResponse.poll_id == poll.id
                    ).count()
                    
                    # Отримуємо варіанти відповіді
                    options = session.query(PollOption).filter(
                        PollOption.poll_id == poll.id
                    ).order_by(PollOption.option_order).all()
                    
                    result.append({
                        'id': poll.id,
                        'question': poll.question,
                        'author_id': poll.author_id,
                        'author_name': author_name,
                        'created_at': poll.created_at,
                        'expires_at': poll.expires_at,
                        'response_count': response_count,
                        'sent_to_users': poll.sent_to_users,
                        'is_anonymous': poll.is_anonymous,
                        'options': [{'id': opt.id, 'text': opt.option_text, 'order': opt.option_order} for opt in options]
                    })
                
                return result
        except Exception as e:
            logger.log_error(f"Помилка отримання активних опитувань: {e}")
            return []
    
    def get_poll_results(self, poll_id: int) -> Optional[Dict[str, Any]]:
        """
        Отримання результатів опитування
        
        Args:
            poll_id: ID опитування
            
        Returns:
            Словник з результатами опитування або None при помилці
        """
        try:
            with get_session() as session:
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    return None
                
                # Отримуємо варіанти відповіді
                options = session.query(PollOption).filter(
                    PollOption.poll_id == poll_id
                ).order_by(PollOption.option_order).all()
                
                # Отримуємо відповіді
                responses = session.query(PollResponse).filter(
                    PollResponse.poll_id == poll_id
                ).all()
                
                # Підраховуємо голоси по кожному варіанту
                option_votes = {opt.id: 0 for opt in options}
                total_votes = len(responses)
                
                for response in responses:
                    if response.option_id in option_votes:
                        option_votes[response.option_id] += 1
                
                # Формуємо результати
                results = []
                for option in options:
                    votes = option_votes.get(option.id, 0)
                    percentage = (votes / total_votes * 100) if total_votes > 0 else 0
                    results.append({
                        'option_id': option.id,
                        'option_text': option.option_text,
                        'votes': votes,
                        'percentage': round(percentage, 1)
                    })
                
                # Отримуємо автора
                author = session.query(User).filter(User.user_id == poll.author_id).first()
                author_name = author.full_name if author and author.full_name else poll.author_username or f"ID: {poll.author_id}"
                
                return {
                    'poll_id': poll.id,
                    'question': poll.question,
                    'author_id': poll.author_id,
                    'author_name': author_name,
                    'created_at': poll.created_at,
                    'closed_at': poll.closed_at,
                    'is_closed': poll.is_closed,
                    'total_votes': total_votes,
                    'results': results
                }
        except Exception as e:
            logger.log_error(f"Помилка отримання результатів опитування: {e}")
            return None
    
    def close_poll(self, poll_id: int) -> bool:
        """
        Закриття опитування
        
        Args:
            poll_id: ID опитування
            
        Returns:
            True якщо опитування успішно закрито
        """
        try:
            with get_session() as session:
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.log_error(f"Опитування {poll_id} не знайдено")
                    return False
                
                if poll.is_closed:
                    logger.log_warning(f"Опитування {poll_id} вже закрите")
                    return False
                
                poll.is_closed = True
                poll.closed_at = datetime.now()
                session.commit()
                
                logger.log_info(f"Опитування {poll_id} закрито")
                return True
        except Exception as e:
            logger.log_error(f"Помилка закриття опитування: {e}")
            return False
    
    def send_poll_report_to_users(self, poll_id: int) -> Dict[str, int]:
        """
        Відправка звіту з результатами опитування всім користувачам
        
        Args:
            poll_id: ID опитування
            
        Returns:
            Словник зі статистикою відправки: {'sent': int, 'failed': int}
        """
        try:
            results = self.get_poll_results(poll_id)
            if not results:
                logger.log_error(f"Не вдалося отримати результати опитування {poll_id}")
                return {'sent': 0, 'failed': 0}
            
            # Перевіряємо, чи опитування анонімне
            with get_session() as session:
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                is_anonymous = poll.is_anonymous if poll else False
            
            # Формуємо текст звіту
            report_text = f"📊 <b>Звіт з опитування</b>"
            if is_anonymous:
                report_text += " 🔒 <i>(Анонімне)</i>"
            report_text += f"\n\n❓ <b>Питання:</b> {results['question']}\n\n"
            report_text += f"📈 <b>Результати:</b>\n"
            
            for result in results['results']:
                bar_length = int(result['percentage'] / 5)  # Один символ = 5%
                bar = "█" * bar_length + "░" * (20 - bar_length)
                report_text += f"\n{result['option_text']}\n"
                report_text += f"{bar} {result['percentage']}% ({result['votes']} голосів)\n"
            
            report_text += f"\n📊 <b>Всього голосів:</b> {results['total_votes']}\n"
            report_text += f"👤 <b>Автор:</b> {results['author_name']}\n"
            report_text += f"📅 <b>Створено:</b> {results['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            if results.get('closed_at'):
                report_text += f"🔒 <b>Закрито:</b> {results['closed_at'].strftime('%d.%m.%Y %H:%M')}"
            
            # Отримуємо список отримувачів опитування
            with get_session() as session:
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.log_error(f"Опитування {poll_id} не знайдено")
                    return {'sent': 0, 'failed': 0}
                
                # Отримуємо список ID отримувачів з опитування
                recipient_user_ids = []
                if poll.recipient_user_ids:
                    try:
                        recipient_user_ids = json.loads(poll.recipient_user_ids)
                    except (json.JSONDecodeError, TypeError):
                        logger.log_warning(f"Не вдалося розпарсити recipient_user_ids для опитування {poll_id}")
                        # Якщо не вдалося розпарсити, використовуємо всіх користувачів (fallback)
                        users = session.query(User).filter(User.role == 'user').all()
                    else:
                        # Отримуємо тільки тих користувачів, яким було відправлено опитування
                        if recipient_user_ids:
                            users = session.query(User).filter(
                                User.role == 'user',
                                User.user_id.in_(recipient_user_ids)
                            ).all()
                        else:
                            users = []
                else:
                    # Якщо список отримувачів не збережено, використовуємо всіх користувачів (fallback для старих опитувань)
                    logger.log_warning(f"Опитування {poll_id} не має збереженого списку отримувачів, використовуємо всіх користувачів")
                    users = session.query(User).filter(User.role == 'user').all()
                
                sent_count = 0
                failed_count = 0
                
                for user in users:
                    try:
                        if not TELEGRAM_API_URL:
                            logger.log_error("TELEGRAM_BOT_TOKEN не встановлено")
                            break
                        
                        response = requests.post(
                            f"{TELEGRAM_API_URL}/sendMessage",
                            json={
                                'chat_id': user.user_id,
                                'text': report_text,
                                'parse_mode': 'HTML'
                            },
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            sent_count += 1
                        else:
                            failed_count += 1
                            logger.log_warning(f"Не вдалося відправити звіт користувачу {user.user_id}: {response.text}")
                    except Exception as e:
                        failed_count += 1
                        logger.log_error(f"Помилка відправки звіту користувачу {user.user_id}: {e}")
                
                # Позначаємо, що звіт відправлено
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if poll:
                    poll.report_sent = True
                    session.commit()
                
                logger.log_info(f"Звіт з опитування {poll_id} відправлено: {sent_count} успішно, {failed_count} помилок")
                return {'sent': sent_count, 'failed': failed_count}
        except Exception as e:
            logger.log_error(f"Помилка відправки звіту з опитування: {e}")
            return {'sent': 0, 'failed': 0}
    
    def send_poll_to_users(self, poll_id: int, user_ids: Optional[List[int]] = None) -> Dict[str, int]:
        """
        Відправка опитування користувачам з кнопками для голосування
        
        Args:
            poll_id: ID опитування
            user_ids: Список ID користувачів для відправки. Якщо None - відправляється всім користувачам
            
        Returns:
            Словник зі статистикою відправки: {'sent': int, 'failed': int}
        """
        try:
            with get_session() as session:
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.log_error(f"Опитування {poll_id} не знайдено")
                    return {'sent': 0, 'failed': 0}
                
                # Отримуємо варіанти відповіді
                options = session.query(PollOption).filter(
                    PollOption.poll_id == poll_id
                ).order_by(PollOption.option_order).all()
                
                if not options:
                    logger.log_error(f"Опитування {poll_id} не має варіантів відповіді")
                    return {'sent': 0, 'failed': 0}
                
                # Формуємо текст опитування
                poll_text = f"📋 <b>Опитування</b>"
                if poll.is_anonymous:
                    poll_text += " 🔒 <i>(Анонімне)</i>"
                poll_text += f"\n\n❓ <b>{poll.question}</b>\n\n"
                
                if poll.expires_at:
                    poll_text += f"⏰ <b>Термін дії:</b> до {poll.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                
                poll_text += "Оберіть варіант відповіді:"
                
                # Створюємо кнопки для кожного варіанту
                keyboard_buttons = []
                for option in options:
                    # Використовуємо callback_data з poll_id та option_id
                    callback_data = f"poll_vote_{poll_id}_{option.id}"
                    keyboard_buttons.append([{
                        'text': f"✅ {option.option_text}",
                        'callback_data': callback_data
                    }])
                
                # Отримуємо список користувачів для відправки
                if user_ids is None:
                    # Відправляємо всім користувачам
                    users = session.query(User).filter(User.role == 'user').all()
                else:
                    # Відправляємо тільки обраним користувачам
                    users = session.query(User).filter(
                        User.role == 'user',
                        User.user_id.in_(user_ids)
                    ).all()
                
                sent_count = 0
                failed_count = 0
                recipient_ids = []  # Зберігаємо список ID отримувачів
                
                for user in users:
                    try:
                        if not TELEGRAM_API_URL:
                            logger.log_error("TELEGRAM_BOT_TOKEN не встановлено")
                            break
                        
                        response = requests.post(
                            f"{TELEGRAM_API_URL}/sendMessage",
                            json={
                                'chat_id': user.user_id,
                                'text': poll_text,
                                'parse_mode': 'HTML',
                                'reply_markup': {
                                    'inline_keyboard': keyboard_buttons
                                }
                            },
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            sent_count += 1
                            recipient_ids.append(user.user_id)  # Додаємо до списку отримувачів
                        else:
                            failed_count += 1
                            logger.log_warning(f"Не вдалося відправити опитування користувачу {user.user_id}: {response.text}")
                    except Exception as e:
                        failed_count += 1
                        logger.log_error(f"Помилка відправки опитування користувачу {user.user_id}: {e}")
                
                # Зберігаємо список отримувачів у JSON форматі
                poll.sent_to_users = True
                poll.recipient_user_ids = json.dumps(recipient_ids) if recipient_ids else None
                session.commit()
                
                logger.log_info(f"Опитування {poll_id} відправлено: {sent_count} успішно, {failed_count} помилок")
                return {'sent': sent_count, 'failed': failed_count}
        except Exception as e:
            logger.log_error(f"Помилка відправки опитування: {e}")
            return {'sent': 0, 'failed': 0}
    
    def add_poll_response(self, poll_id: int, option_id: int, user_id: int) -> bool:
        """
        Додавання відповіді користувача на опитування
        
        Args:
            poll_id: ID опитування
            option_id: ID варіанту відповіді
            user_id: ID користувача
            
        Returns:
            True якщо відповідь успішно додано
        """
        try:
            with get_session() as session:
                # Перевіряємо чи опитування існує та не закрите
                poll = session.query(Poll).filter(Poll.id == poll_id).first()
                if not poll:
                    logger.log_error(f"Опитування {poll_id} не знайдено")
                    return False
                
                if poll.is_closed:
                    logger.log_warning(f"Опитування {poll_id} вже закрите")
                    return False
                
                # Перевіряємо чи користувач вже відповів
                existing_response = session.query(PollResponse).filter(
                    PollResponse.poll_id == poll_id,
                    PollResponse.user_id == user_id
                ).first()
                
                if existing_response:
                    # Оновлюємо існуючу відповідь
                    existing_response.option_id = option_id
                    existing_response.responded_at = datetime.now()
                else:
                    # Створюємо нову відповідь
                    response = PollResponse(
                        poll_id=poll_id,
                        option_id=option_id,
                        user_id=user_id
                    )
                    session.add(response)
                
                session.commit()
                logger.log_info(f"Відповідь користувача {user_id} на опитування {poll_id} збережено")
                return True
        except Exception as e:
            logger.log_error(f"Помилка додавання відповіді на опитування: {e}")
            return False
    
    def check_and_close_expired_polls(self) -> int:
        """
        Перевірка та автоматичне закриття опитувань з закінченим терміном дії
        
        Returns:
            Кількість закритих опитувань
        """
        try:
            closed_count = 0
            with get_session() as session:
                now = datetime.now()
                
                # Знаходимо опитування з закінченим терміном дії
                expired_polls = session.query(Poll).filter(
                    Poll.is_closed == False,
                    Poll.expires_at.isnot(None),
                    Poll.expires_at <= now
                ).all()
                
                for poll in expired_polls:
                    poll.is_closed = True
                    poll.closed_at = now
                    
                    # Відправляємо звіт
                    self.send_poll_report_to_users(poll.id)
                    
                    closed_count += 1
                    logger.log_info(f"Опитування {poll.id} автоматично закрито (термін дії закінчився)")
                
                session.commit()
                return closed_count
        except Exception as e:
            logger.log_error(f"Помилка перевірки термінів дії опитувань: {e}")
            return 0


# Глобальний екземпляр менеджера опитувань
_poll_manager: Optional[PollManager] = None


def get_poll_manager() -> PollManager:
    """
    Отримання глобального менеджера опитувань
    
    Returns:
        Екземпляр PollManager
    """
    global _poll_manager
    if _poll_manager is None:
        _poll_manager = PollManager()
    return _poll_manager

