"""
Модуль для роботи з API повітряних тривог alerts.in.ua
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error
from dotenv import load_dotenv

from logger import logger

# Завантажуємо змінні середовища
load_dotenv("config.env")


class AirAlertManager:
    """Менеджер для роботи з API повітряних тривог alerts.in.ua"""
    
    def __init__(self, city: str = "Дніпро", update_interval: int = 60):
        """
        Ініціалізація менеджера повітряних тривог
        
        Args:
            city: Назва міста для перевірки тривоги
            update_interval: Інтервал оновлення в секундах
        """
        self.city = city
        self.update_interval = update_interval
        self.api_token = os.getenv("ALERTS_API_TOKEN", "fcf3d777680f8c9020b76516bf8ed2d50766b346ab2203")
        self.api_url = f"https://api.alerts.in.ua/v1/alerts/active.json?token={self.api_token}"
        self.last_update = None
        self.alert_status = False
        self.active_alerts = []
        self.last_check_time = None
        self.is_updating = False
        self.previous_alert_status = False  # Для відстеження зміни статусу
        self.previous_alert_types = set()  # Для відстеження зміни типів тривог
        
    async def get_alert_status(self) -> bool:
        """
        Отримання поточного статусу повітряної тривоги
        
        Returns:
            True якщо тривога активна, False якщо ні
        """
        try:
            # Перевіряємо чи потрібно оновлювати дані
            if self._should_update():
                await self._update_alert_status()
            
            return self.alert_status
            
        except Exception as e:
            logger.log_error(f"Помилка отримання статусу тривоги: {e}")
            return False
    
    def _should_update(self) -> bool:
        """Перевірка чи потрібно оновлювати дані"""
        if self.last_update is None:
            return True
        
        time_since_update = datetime.now() - self.last_update
        return time_since_update.total_seconds() >= self.update_interval
    
    async def _update_alert_status(self) -> None:
        """Оновлення статусу тривоги з API alerts.in.ua"""
        if self.is_updating:
            return  # Уникаємо одночасних оновлень
        
        self.is_updating = True
        
        try:
            # Виконуємо HTTP запит в окремому потоці
            loop = asyncio.get_event_loop()
            region_alerts = await loop.run_in_executor(None, self._fetch_api_data)
            
            if region_alerts is not None:
                # Визначаємо статус тривоги
                new_alert_status = len(region_alerts) > 0
                
                # Отримуємо типи тривог (унікальні)
                current_alert_types = set(alert.get('alert_type', 'unknown') for alert in region_alerts)
                
                # Логуємо тільки при зміні статусу або зміні типів тривог
                status_changed = new_alert_status != self.previous_alert_status
                types_changed = current_alert_types != self.previous_alert_types
                
                if status_changed or types_changed:
                    if new_alert_status:
                        alert_types_list = list(current_alert_types)
                        logger.log_info(f"🚨 Активні тривоги в {self.city}: {alert_types_list}")
                    else:
                        logger.log_info(f"✅ Тривоги в {self.city} припинилися")
                
                # Оновлюємо список активних тривог
                self.active_alerts = region_alerts
                self.alert_status = new_alert_status
                self.previous_alert_status = new_alert_status
                self.previous_alert_types = current_alert_types
                
                self.last_update = datetime.now()
                self.last_check_time = datetime.now()
            else:
                logger.log_error("Не вдалося отримати дані з API тривог")
                
        except Exception as e:
            logger.log_error(f"Помилка оновлення статусу тривоги: {e}")
        finally:
            self.is_updating = False
    
    def _fetch_api_data(self) -> Optional[List[Dict[str, Any]]]:
        """
        Синхронне отримання даних з API alerts.in.ua
        
        Returns:
            Список активних тривог для міста або None при помилці
        """
        try:
            with urllib.request.urlopen(self.api_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Отримуємо список активних тривог
                alerts = data.get('alerts', [])
                
                # Фільтруємо тривоги для міста Дніпро
                city_alerts = [
                    alert for alert in alerts 
                    if 'дніпро' in alert.get('location_title', '').lower() or 
                       'днепр' in alert.get('location_title', '').lower()
                ]
                
                return city_alerts
                    
        except urllib.error.URLError as e:
            logger.log_error(f"Помилка з'єднання з API тривог: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.log_error(f"Помилка парсингу JSON з API тривог: {e}")
            return None
        except Exception as e:
            logger.log_error(f"Неочікувана помилка при отриманні даних API: {e}")
            return None
    
    def get_alert_indicator(self) -> str:
        """
        Отримання індикатора статусу тривоги для відображення
        
        Returns:
            Рядок з індикатором статусу
        """
        if self.alert_status and self.active_alerts:
            # Отримуємо типи тривог
            alert_types = set(alert.get('alert_type', 'unknown') for alert in self.active_alerts)
            
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
            
            # Отримуємо час початку найранішої тривоги
            earliest_start = None
            for alert in self.active_alerts:
                started_at = alert.get('started_at')
                if started_at:
                    try:
                        dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        if earliest_start is None or dt < earliest_start:
                            earliest_start = dt
                    except:
                        pass
            
            time_info = ""
            if earliest_start:
                time_str = earliest_start.strftime('%d.%m %H:%M')
                time_info = f" (з {time_str})"
            
            return f"{emoji} **{alert_text} В {self.city.upper()}!**{time_info}"
        else:
            return f"✅ **В {self.city.upper()} ТИХО**"
    
    def get_alert_status_text(self) -> str:
        """
        Отримання тексту статусу тривоги
        
        Returns:
            Рядок з описом статусу
        """
        if self.last_check_time is None:
            return "❓ Статус невідомий"
        
        time_ago = datetime.now() - self.last_check_time
        minutes_ago = int(time_ago.total_seconds() / 60)
        
        if self.alert_status and self.active_alerts:
            # Отримуємо детальну інформацію про тривоги
            alert_details = []
            for alert in self.active_alerts:
                location = alert.get('location_title', 'Невідомо')
                alert_type = alert.get('alert_type', 'unknown')
                started_at = alert.get('started_at', '')
                
                # Перетворюємо тип тривоги на українську
                type_translation = {
                    'air_raid': 'Повітряна тривога',
                    'artillery_shelling': 'Артилерійський обстріл',
                    'urban_fights': 'Міські бої'
                }
                
                alert_type_ua = type_translation.get(alert_type, alert_type)
                alert_details.append(f"{location}: {alert_type_ua}")
            
            details_text = " | ".join(alert_details[:3])  # Показуємо максимум 3 тривоги
            if len(alert_details) > 3:
                details_text += f" та ще {len(alert_details) - 3}"
            
            return f"🚨 У {self.city} активні тривоги: {details_text} (оновлено {minutes_ago} хв тому)"
        else:
            return f"✅ У {self.city} зараз тихо (оновлено {minutes_ago} хв тому)"
    
    async def start_periodic_update(self) -> None:
        """Запуск періодичного оновлення статусу"""
        logger.log_info("Запуск періодичного оновлення статусу тривоги")
        
        while True:
            try:
                await self._update_alert_status()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.log_error(f"Помилка в періодичному оновленні: {e}")
                await asyncio.sleep(30)  # Чекаємо 30 секунд перед повторною спробою


# Глобальний екземпляр менеджера
AIR_ALERT_CITY = os.getenv("AIR_ALERT_CITY", "Дніпро")
air_alert_manager = AirAlertManager(city=AIR_ALERT_CITY)


def get_air_alert_manager() -> AirAlertManager:
    """Отримання глобального менеджера повітряних тривог"""
    return air_alert_manager
