"""
Скрипт для резервного копіювання бази даних та конфігурації TeachHub
"""
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Додаємо поточну директорію в Python path
sys.path.insert(0, os.path.dirname(__file__))

from database import get_session
from logger import logger


def backup_database(backup_dir: str = "backups") -> str:
    """
    Резервне копіювання бази даних
    
    Args:
        backup_dir: Директорія для збереження backup
        
    Returns:
        Шлях до створеного backup файлу
    """
    try:
        # Створюємо директорію для backup якщо не існує
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Шлях до бази даних
        db_path = Path("schedule_bot.db")
        if not db_path.exists():
            print(f"❌ База даних не знайдена: {db_path}")
            return None
        
        # Формуємо ім'я файлу з датою та часом
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"schedule_bot_backup_{timestamp}.db"
        backup_filepath = backup_path / backup_filename
        
        # Копіюємо базу даних
        shutil.copy2(db_path, backup_filepath)
        
        # Отримуємо розмір файлу
        file_size = backup_filepath.stat().st_size / (1024 * 1024)  # MB
        
        print(f"✅ Backup створено: {backup_filepath}")
        print(f"   Розмір: {file_size:.2f} MB")
        
        logger.log_info(f"Створено backup бази даних: {backup_filepath} ({file_size:.2f} MB)")
        
        return str(backup_filepath)
        
    except Exception as e:
        print(f"❌ Помилка створення backup: {e}")
        logger.log_error(f"Помилка створення backup: {e}")
        return None


def backup_config(backup_dir: str = "backups") -> str:
    """
    Резервне копіювання конфігурації
    
    Args:
        backup_dir: Директорія для збереження backup
        
    Returns:
        Шлях до створеного backup файлу
    """
    try:
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        config_path = Path("config.env")
        if not config_path.exists():
            print(f"⚠️ Файл конфігурації не знайдено: {config_path}")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"config_backup_{timestamp}.env"
        backup_filepath = backup_path / backup_filename
        
        shutil.copy2(config_path, backup_filepath)
        
        print(f"✅ Backup конфігурації створено: {backup_filepath}")
        logger.log_info(f"Створено backup конфігурації: {backup_filepath}")
        
        return str(backup_filepath)
        
    except Exception as e:
        print(f"❌ Помилка створення backup конфігурації: {e}")
        logger.log_error(f"Помилка створення backup конфігурації: {e}")
        return None


def cleanup_old_backups(backup_dir: str = "backups", keep_days: int = 30):
    """
    Видалення старих backup файлів
    
    Args:
        backup_dir: Директорія з backup файлами
        keep_days: Скільки днів зберігати backup
    """
    try:
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            return
        
        cutoff_date = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
        deleted_count = 0
        
        for file in backup_path.glob("*.db"):
            if file.stat().st_mtime < cutoff_date:
                file.unlink()
                deleted_count += 1
        
        for file in backup_path.glob("*.env"):
            if file.stat().st_mtime < cutoff_date:
                file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            print(f"✅ Видалено {deleted_count} старих backup файлів")
            logger.log_info(f"Видалено {deleted_count} старих backup файлів")
        
    except Exception as e:
        print(f"⚠️ Помилка очищення старих backup: {e}")
        logger.log_warning(f"Помилка очищення старих backup: {e}")


def main():
    """Головна функція"""
    print("=" * 60)
    print("💾 Резервне копіювання TeachHub")
    print("=" * 60)
    print()
    
    # Створюємо backup бази даних
    db_backup = backup_database()
    
    # Створюємо backup конфігурації
    config_backup = backup_config()
    
    # Очищаємо старі backup (зберігаємо 30 днів)
    cleanup_old_backups(keep_days=30)
    
    print()
    print("=" * 60)
    if db_backup or config_backup:
        print("✅ Backup завершено успішно")
    else:
        print("⚠️ Backup не створено")
    print("=" * 60)


if __name__ == "__main__":
    main()

