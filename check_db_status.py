"""
Утиліта для перевірки стану БД та WAL mode
Використовується для діагностики проблем з конкурентним доступом
"""
import sqlite3
import os
from datetime import datetime


def check_database_status(db_path: str = "schedule_bot.db"):
    """
    Перевірка статусу БД
    
    Args:
        db_path: Шлях до файлу БД
    """
    print("=" * 60)
    print("🔍 ДІАГНОСТИКА БАЗИ ДАНИХ")
    print("=" * 60)
    print()
    
    # Перевірка існування файлу
    if not os.path.exists(db_path):
        print(f"❌ Файл БД не знайдено: {db_path}")
        return
    
    print(f"✅ Файл БД знайдено: {db_path}")
    print(f"📦 Розмір: {os.path.getsize(db_path) / 1024:.2f} KB")
    print()
    
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        
        # Перевірка journal mode
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        print(f"📝 Journal Mode: {journal_mode}")
        
        if journal_mode.lower() == 'wal':
            print("   ✅ WAL mode увімкнений (підтримка конкурентного доступу)")
        else:
            print("   ⚠️ WAL mode ВИМКНЕНИЙ! Рекомендується увімкнути:")
            print("   sqlite3 schedule_bot.db \"PRAGMA journal_mode=WAL;\"")
        print()
        
        # Перевірка busy timeout
        cursor.execute("PRAGMA busy_timeout;")
        busy_timeout = cursor.fetchone()[0]
        print(f"⏱️ Busy Timeout: {busy_timeout} мс")
        
        if busy_timeout >= 30000:
            print("   ✅ Timeout достатній (≥30 секунд)")
        else:
            print("   ⚠️ Timeout малий! Можливі помилки блокування")
        print()
        
        # Перевірка foreign keys
        cursor.execute("PRAGMA foreign_keys;")
        foreign_keys = cursor.fetchone()[0]
        print(f"🔗 Foreign Keys: {'✅ Увімкнені' if foreign_keys else '❌ Вимкнені'}")
        print()
        
        # Перевірка таблиць
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = cursor.fetchall()
        print(f"📋 Таблиці БД ({len(tables)}):")
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            print(f"   • {table_name}: {count} записів")
        print()
        
        # Перевірка WAL файлів
        wal_file = f"{db_path}-wal"
        shm_file = f"{db_path}-shm"
        
        print("📁 WAL файли:")
        if os.path.exists(wal_file):
            wal_size = os.path.getsize(wal_file) / 1024
            print(f"   ✅ {wal_file} ({wal_size:.2f} KB)")
        else:
            print(f"   ℹ️ {wal_file} (не існує - це нормально якщо немає активних транзакцій)")
        
        if os.path.exists(shm_file):
            print(f"   ✅ {shm_file} (shared memory)")
        else:
            print(f"   ℹ️ {shm_file} (не існує)")
        print()
        
        # Перевірка активних з'єднань
        cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")
        checkpoint_result = cursor.fetchone()
        print(f"🔄 WAL Checkpoint: {checkpoint_result}")
        print()
        
        conn.close()
        
        print("=" * 60)
        print("✅ ДІАГНОСТИКА ЗАВЕРШЕНА")
        print("=" * 60)
        print()
        print("💡 Рекомендації:")
        print("   1. WAL mode має бути увімкнений")
        print("   2. Busy timeout >= 30000 мс")
        print("   3. Foreign keys увімкнені")
        print("   4. Регулярно робіть backup БД")
        print()
        
    except Exception as e:
        print(f"❌ Помилка діагностики: {e}")


def enable_wal_mode(db_path: str = "schedule_bot.db"):
    """
    Увімкнення WAL mode для БД
    
    Args:
        db_path: Шлях до файлу БД
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        result = cursor.fetchone()[0]
        conn.close()
        
        print(f"✅ WAL mode увімкнено: {result}")
        return True
    except Exception as e:
        print(f"❌ Помилка увімкнення WAL: {e}")
        return False


def run_checkpoint(db_path: str = "schedule_bot.db"):
    """
    Запуск checkpoint для очищення WAL журналу
    
    Args:
        db_path: Шлях до файлу БД
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        result = cursor.fetchone()
        conn.close()
        
        print(f"✅ Checkpoint виконано: {result}")
        return True
    except Exception as e:
        print(f"❌ Помилка checkpoint: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "check":
            check_database_status()
        elif command == "wal":
            enable_wal_mode()
        elif command == "checkpoint":
            run_checkpoint()
        else:
            print(f"❌ Невідома команда: {command}")
            print("\nДоступні команди:")
            print("  python check_db_status.py check      - діагностика БД")
            print("  python check_db_status.py wal        - увімкнути WAL mode")
            print("  python check_db_status.py checkpoint - очистити WAL журнал")
    else:
        # За замовчуванням - діагностика
        check_database_status()



