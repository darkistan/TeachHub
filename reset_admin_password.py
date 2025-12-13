#!/usr/bin/env python3
"""
Скрипт для відновлення пароля адміністратора
Використовується, коли адмін забув пароль після зміни стандартного
"""
import os
import sys
from werkzeug.security import generate_password_hash

# Додаємо батьківську директорію в Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from database import init_database, get_session
from models import User

def reset_admin_password(new_password: str = None):
    """
    Відновлення пароля адміністратора
    
    Args:
        new_password: Новий пароль (якщо не вказано, буде запропоновано ввести)
    """
    # Ініціалізуємо БД
    init_database()
    
    if not new_password:
        print("=" * 60)
        print("Відновлення пароля адміністратора")
        print("=" * 60)
        print()
        new_password = input("Введіть новий пароль для адміністратора: ").strip()
        
        if not new_password:
            print("❌ Помилка: Пароль не може бути порожнім!")
            return False
        
        if len(new_password) < 6:
            print("❌ Помилка: Пароль повинен містити мінімум 6 символів!")
            return False
        
        confirm_password = input("Підтвердіть пароль: ").strip()
        
        if new_password != confirm_password:
            print("❌ Помилка: Паролі не співпадають!")
            return False
    
    try:
        with get_session() as session:
            # Знаходимо адміністратора
            admin = session.query(User).filter(User.role == 'admin').first()
            
            if not admin:
                print("❌ Помилка: Адміністратор не знайдено в базі даних!")
                print("   Переконайтеся, що в системі є користувач з role='admin'")
                return False
            
            # Оновлюємо пароль
            admin.password_hash = generate_password_hash(new_password)
            session.commit()
            
            print("=" * 60)
            print("✅ Пароль адміністратора успішно оновлено!")
            print("=" * 60)
            print(f"User ID: {admin.user_id}")
            print(f"Username: @{admin.username}")
            print(f"ПІБ: {admin.full_name or 'Не встановлено'}")
            print()
            print("Тепер ви можете увійти в веб-інтерфейс з новим паролем.")
            print("=" * 60)
            
            return True
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Відновлення пароля адміністратора')
    parser.add_argument('--password', '-p', type=str, help='Новий пароль (опціонально)')
    
    args = parser.parse_args()
    
    success = reset_admin_password(args.password)
    sys.exit(0 if success else 1)

