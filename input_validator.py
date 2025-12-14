"""
Модуль для валідації вхідних даних
"""
import re
from typing import Dict, Any, Optional

from logger import logger


class InputValidator:
    """Клас для валідації вхідних даних"""
    
    def __init__(self):
        """Ініціалізація валідатора"""
        # Налаштування
        self.max_message_length = 1000  # Максимальна довжина повідомлення
        self.max_query_length = 200  # Максимальна довжина запиту
    
    def validate_message_length(self, message: str) -> Dict[str, Any]:
        """
        Валідація довжини повідомлення
        
        Args:
            message: Повідомлення для перевірки
            
        Returns:
            Результат валідації
        """
        if not message:
            return {
                "valid": False,
                "message": "Повідомлення не може бути порожнім"
            }
        
        if len(message) > self.max_message_length:
            logger.log_error(f"Повідомлення занадто довге: {len(message)} символів")
            return {
                "valid": False,
                "message": f"Повідомлення занадто довге. Максимум {self.max_message_length} символів.",
                "current_length": len(message),
                "max_length": self.max_message_length
            }
        
        return {
            "valid": True,
            "message": "Повідомлення валідне"
        }
    
    def validate_week_type(self, week_type: str) -> Dict[str, Any]:
        """
        Валідація типу тижня
        
        Args:
            week_type: Тип тижня для перевірки
            
        Returns:
            Результат валідації
        """
        if not week_type:
            return {
                "valid": False,
                "message": "Тип тижня не може бути порожнім"
            }
        
        week_type = week_type.strip().lower()
        
        if week_type not in ["numerator", "denominator", "чисельник", "знаменник"]:
            logger.log_error(f"Невірний тип тижня: {week_type}")
            return {
                "valid": False,
                "message": "Невірний тип тижня. Доступні: numerator, denominator"
            }
        
        # Конвертуємо українські назви в англійські
        if week_type in ["чисельник"]:
            week_type = "numerator"
        elif week_type in ["знаменник"]:
            week_type = "denominator"
        
        return {
            "valid": True,
            "message": "Тип тижня валідний",
            "cleaned_week_type": week_type
        }
    
    def validate_day_name(self, day: str) -> Dict[str, Any]:
        """
        Валідація назви дня
        
        Args:
            day: Назва дня для перевірки
            
        Returns:
            Результат валідації
        """
        if not day:
            return {
                "valid": False,
                "message": "Назва дня не може бути порожньою"
            }
        
        day = day.strip().lower()
        
        # Словник для конвертації українських назв
        day_mapping = {
            "понеділок": "monday",
            "вівторок": "tuesday",
            "середа": "wednesday",
            "четвер": "thursday",
            "п'ятниця": "friday",
            "субота": "saturday",
            "неділя": "sunday"
        }
        
        valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
        # Перевіряємо англійські назви
        if day in valid_days:
            return {
                "valid": True,
                "message": "Назва дня валідна",
                "cleaned_day": day
            }
        
        # Перевіряємо українські назви
        if day in day_mapping:
            return {
                "valid": True,
                "message": "Назва дня валідна",
                "cleaned_day": day_mapping[day]
            }
        
        logger.log_error(f"Невірна назва дня: {day}")
        return {
            "valid": False,
            "message": f"Невірна назва дня. Доступні: {', '.join(day_mapping.keys())}"
        }
    
    def sanitize_input(self, text: str) -> str:
        """
        Санітизація вхідного тексту
        
        Args:
            text: Текст для санітизації
            
        Returns:
            Санітизований текст
        """
        if not text:
            return ""
        
        # Видаляємо зайві пробіли
        text = text.strip()
        
        # Обмежуємо довжину
        if len(text) > self.max_message_length:
            text = text[:self.max_message_length]
        
        return text
    
    def validate_role(self, role: str) -> bool:
        """
        Валідація ролі користувача
        
        Args:
            role: Роль для перевірки
            
        Returns:
            True якщо роль валідна, False інакше
        """
        if not role:
            return False
        
        valid_roles = ['admin', 'user']
        return role.lower() in valid_roles


# Глобальний екземпляр валідатора
input_validator = InputValidator()
