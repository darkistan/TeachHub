"""
Скрипт для видалення загальних записів без teacher_user_id
Видаляє заняття та періоди, які не прив'язані до конкретного викладача
"""
import sys
import os

# Додаємо поточну директорію в Python path
sys.path.insert(0, os.path.dirname(__file__))

from database import get_session
from models import ScheduleEntry, AcademicPeriod

def cleanup_orphaned_data():
    """Видалення загальних записів без teacher_user_id"""
    print("=" * 60)
    print("Очищення загальних записів з бази даних")
    print("=" * 60)
    print()
    
    try:
        with get_session() as session:
            # Підраховуємо записи перед видаленням
            schedule_count = session.query(ScheduleEntry).filter(
                ScheduleEntry.teacher_user_id.is_(None)
            ).count()
            
            periods_count = session.query(AcademicPeriod).filter(
                AcademicPeriod.teacher_user_id.is_(None)
            ).count()
            
            if schedule_count == 0 and periods_count == 0:
                print("✅ Загальних записів не знайдено. База даних вже очищена.")
                return
            
            print(f"Знайдено загальних записів:")
            print(f"  - Заняття: {schedule_count}")
            print(f"  - Періоди: {periods_count}")
            print()
            
            confirm = input("Видалити ці записи? (y/n): ").strip().lower()
            if confirm != 'y':
                print("Скасовано.")
                return
            
            # Видаляємо заняття без teacher_user_id
            deleted_schedule = session.query(ScheduleEntry).filter(
                ScheduleEntry.teacher_user_id.is_(None)
            ).delete()
            
            # Видаляємо періоди без teacher_user_id
            deleted_periods = session.query(AcademicPeriod).filter(
                AcademicPeriod.teacher_user_id.is_(None)
            ).delete()
            
            session.commit()
            
            print()
            print("✅ Очищення завершено!")
            print(f"  - Видалено заняття: {deleted_schedule}")
            print(f"  - Видалено періодів: {deleted_periods}")
            
    except Exception as e:
        print(f"\n❌ Помилка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    cleanup_orphaned_data()

