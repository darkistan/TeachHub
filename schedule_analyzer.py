"""
Модуль для аналізу навчального графіку через БД
"""
from datetime import datetime, date
from typing import Dict, Tuple, Optional

from database import get_session
from models import AcademicPeriod, ScheduleMetadata


class ScheduleAnalyzer:
    """Аналізатор навчального графіку через БД"""
    
    def __init__(self):
        """Ініціалізація аналізатора"""
        pass
    
    def _load_data_from_db(self) -> Dict:
        """Завантаження даних з БД"""
        try:
            with get_session() as session:
                metadata = session.query(ScheduleMetadata).first()
                periods = session.query(AcademicPeriod).all()
                
                return {
                    'metadata': metadata,
                    'periods': {p.period_id: {
                        'name': p.name,
                        'start': datetime.strptime(p.start_date, "%Y-%m-%d").date(),
                        'end': datetime.strptime(p.end_date, "%Y-%m-%d").date(),
                        'weeks': p.weeks,
                        'color': p.color,
                        'description': p.description
                    } for p in periods}
                }
        except Exception as e:
            return {'metadata': None, 'periods': {}}
    
    def get_current_period(self, current_date: Optional[date] = None) -> Tuple[str, Dict]:
        """Визначає поточний період навчання"""
        if current_date is None:
            current_date = date.today()
        
        data = self._load_data_from_db()
        periods = data['periods']
        
        for period_id, period_data in periods.items():
            if period_data["start"] <= current_date <= period_data["end"]:
                return period_id, period_data
        
        return "unknown", {"name": "Невідомий період", "color": "❓"}
    
    def calculate_progress(self, current_date: Optional[date] = None) -> Dict:
        """Розраховує прогрес навчального року"""
        if current_date is None:
            current_date = date.today()
        
        data = self._load_data_from_db()
        periods = data['periods']
        metadata = data['metadata']
        
        progress = {}
        
        for period_id, period_data in periods.items():
            if current_date < period_data["start"]:
                status, period_progress = "not_started", 0
            elif current_date > period_data["end"]:
                status, period_progress = "completed", 100
            else:
                status = "in_progress"
                days_passed = (current_date - period_data["start"]).days + 1
                total_days = (period_data["end"] - period_data["start"]).days + 1
                period_progress = min(100, max(0, (days_passed / total_days) * 100))
            
            progress[period_id] = {
                "name": period_data["name"],
                "progress": round(period_progress, 1),
                "status": status,
                "color": period_data["color"],
                "weeks": period_data["weeks"],
                "start_date": period_data["start"],
                "end_date": period_data["end"]
            }
        
        return progress
    
    def create_progress_bar(self, progress: float, length: int = 10) -> str:
        """Створює прогрес-бар"""
        filled = int((progress / 100) * length)
        return f"[{'█' * filled}{'░' * (length - filled)}] {progress:.1f}%"
    
    def format_progress_report(self, current_date: Optional[date] = None) -> str:
        """Форматує звіт про прогрес"""
        if current_date is None:
            current_date = date.today()
        
        progress = self.calculate_progress(current_date)
        current_period, current_period_data = self.get_current_period(current_date)
        
        data = self._load_data_from_db()
        metadata = data['metadata']
        
        group_name = metadata.group_name if metadata else "KCM-24-11"
        
        report_parts = [
            f"📊 **Прогрес навчання групи {group_name}**",
            f"📅 Дата: {current_date.strftime('%d.%m.%Y')}",
            f"🎯 Поточний період: {current_period_data['name']}",
            "─" * 50
        ]
        
        for period_id, period_info in progress.items():
            status_emoji = {"not_started": "⏳", "in_progress": "🔄", "completed": "✅"}.get(period_info["status"], "❓")
            progress_bar = self.create_progress_bar(period_info["progress"], 15)
            
            time_info = ""
            if period_info["status"] == "in_progress":
                days_left = (period_info["end_date"] - current_date).days
                time_info = f" (залишилось {days_left} днів)" if days_left > 0 else " (завершується сьогодні)"
            elif period_info["status"] == "not_started":
                days_until = (period_info["start_date"] - current_date).days
                time_info = f" (через {days_until} днів)" if days_until > 0 else ""
            
            report_parts.append(
                f"{status_emoji} **{period_info['name']}**\n"
                f"   {progress_bar}{time_info}\n"
                f"   📅 {period_info['start_date'].strftime('%d.%m')} - {period_info['end_date'].strftime('%d.%m')} "
                f"({period_info['weeks']} тижнів)"
            )
        
        return "\n".join(report_parts)
    
    def format_full_schedule(self) -> str:
        """Форматує повний графік навчання"""
        data = self._load_data_from_db()
        metadata = data['metadata']
        periods = data['periods']
        
        group_name = metadata.group_name if metadata else "KCM-24-11"
        academic_year = metadata.academic_year if metadata else "2025/2026"
        
        return f"📚 **Повний графік групи {group_name}**\n🎓 Рік: {academic_year}\n\n(Детальний графік тут)"


# Глобальний екземпляр
schedule_analyzer = ScheduleAnalyzer()

