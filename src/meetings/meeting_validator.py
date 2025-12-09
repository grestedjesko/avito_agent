import yaml
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import pytz


class MeetingValidator:
    def __init__(self, rules_file: str = "data/meeting_rules.yaml"):
        self.rules_file = Path(rules_file)
        self.rules: Dict = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        if not self.rules_file.exists():
            return
        
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                self.rules = yaml.safe_load(f)
        except Exception as e:
            pass
    
    def _normalize_fuzzy_time(self, time_str: str) -> str:
        """Преобразует нечеткие временные выражения в конкретное время"""
        time_lower = time_str.lower().strip()
        
        # Маппинг нечетких времен на конкретные часы
        fuzzy_times = {
            'утром': '10:00',
            'утро': '10:00',
            'днем': '14:00',
            'днём': '14:00',
            'день': '14:00',
            'вечером': '18:00',
            'вечер': '18:00',
            'ночью': '20:00',
            'ночь': '20:00'
        }
        
        return fuzzy_times.get(time_lower, time_str)
    
    def _parse_time(self, time_str: str) -> tuple:
        parts = time_str.split(':')
        return int(parts[0]), int(parts[1])
    
    def _get_datetime(
        self,
        date_str: str,
        time_str: str,
        tz_name: Optional[str] = None
    ) -> datetime:
        if date_str.lower() == "сегодня":
            date = datetime.now().date()
        elif date_str.lower() == "завтра":
            date = (datetime.now() + timedelta(days=1)).date()
        else:
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    date = datetime.strptime(date_str, "%d.%m.%Y").date()
                except ValueError:
                    date = (datetime.now() + timedelta(days=1)).date()
        
        hour, minute = self._parse_time(time_str)
        
        dt = datetime.combine(date, datetime.min.time().replace(hour=hour, minute=minute))
        
        if tz_name:
            tz = pytz.timezone(tz_name)
            dt = tz.localize(dt)
        
        return dt
    
    def validate_meeting_time(
        self,
        date_str: str,
        time_str: str,
        location: Optional[str] = None
    ) -> Tuple[bool, List[str], Optional[str]]:
        issues = []
        suggestion = None
        
        # Нормализуем нечеткое время
        time_str = self._normalize_fuzzy_time(time_str)
        
        tz_name = self.rules.get('business_hours', {}).get('timezone', 'Europe/Moscow')
        
        try:
            meeting_dt = self._get_datetime(date_str, time_str, tz_name)
            now = datetime.now(pytz.timezone(tz_name))
        except Exception as e:
            return False, [f"Ошибка разбора даты/времени: {e}"], None
        
        if meeting_dt < now:
            issues.append("Указанное время уже прошло")
            preferred_times = self.rules.get('special_rules', {}).get('preferred_times', ['10:00', '14:00', '18:00'])
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%A')
            suggestion = f"Это время уже прошло. Можем встретиться завтра в {preferred_times[0]} или {preferred_times[1]}?"
            return False, issues, suggestion
        
        lead_time_rules = self.rules.get('lead_time', {})
        min_hours = lead_time_rules.get('min_hours', 2)
        max_days = lead_time_rules.get('max_days', 30)
        
        time_diff = meeting_dt - now
        hours_diff = time_diff.total_seconds() / 3600
        days_diff = time_diff.days
        
        if hours_diff < min_hours:
            messages = self.rules.get('messages', {})
            earliest_dt = now + timedelta(hours=min_hours)
            preferred_times = self.rules.get('special_rules', {}).get('preferred_times', ['10:00', '14:00', '18:00'])
            earliest_time = earliest_dt.strftime('%H:%M')
            
            next_slots = [t for t in preferred_times if t > earliest_time]
            if next_slots:
                suggestion = f"Мне нужно минимум {min_hours} часа для подготовки. Могу встретиться сегодня в {next_slots[0]} или завтра?"
            else:
                suggestion = f"Мне нужно минимум {min_hours} часа для подготовки. Могу встретиться завтра в {preferred_times[0]} или {preferred_times[1]}?"
            
            issues.append(f"Слишком скоро (нужно минимум {min_hours} часа)")
            return False, issues, suggestion
        
        if days_diff > max_days:
            messages = self.rules.get('messages', {})
            suggestion = messages.get('too_far', '').format(days=max_days)
            issues.append(f"Слишком далеко (максимум {max_days} дней)")
            return False, issues, suggestion
        
        working_days = self.rules.get('working_days', {})
        weekday_name = meeting_dt.strftime('%A').lower()
        
        day_map = {
            'monday': 'monday', 'tuesday': 'tuesday', 'wednesday': 'wednesday',
            'thursday': 'thursday', 'friday': 'friday', 'saturday': 'saturday',
            'sunday': 'sunday'
        }
        
        day_key = day_map.get(weekday_name, weekday_name)
        
        if not working_days.get(day_key, True):
            messages = self.rules.get('messages', {})
            suggestion = messages.get('non_working_day', '').format(day=weekday_name)
            issues.append(f"В {weekday_name} выходной")
            return False, issues, suggestion
        
        business_hours = self.rules.get('business_hours', {})
        if business_hours.get('enabled', True):
            start_hour, start_minute = self._parse_time(business_hours.get('start_time', '09:00'))
            end_hour, end_minute = self._parse_time(business_hours.get('end_time', '20:00'))
            
            meeting_time = meeting_dt.time()
            start_time = datetime.min.time().replace(hour=start_hour, minute=start_minute)
            end_time = datetime.min.time().replace(hour=end_hour, minute=end_minute)
            
            if not (start_time <= meeting_time <= end_time):
                messages = self.rules.get('messages', {})
                suggestion = messages.get('business_hours_violation', '').format(
                    start=business_hours.get('start_time'),
                    end=business_hours.get('end_time')
                )
                issues.append(f"Время вне рабочих часов")
                return False, issues, suggestion
        
        lunch_break = self.rules.get('lunch_break', {})
        if lunch_break.get('enabled', False):
            lunch_start_hour, lunch_start_minute = self._parse_time(lunch_break.get('start_time', '13:00'))
            lunch_end_hour, lunch_end_minute = self._parse_time(lunch_break.get('end_time', '14:00'))
            
            lunch_start = datetime.min.time().replace(hour=lunch_start_hour, minute=lunch_start_minute)
            lunch_end = datetime.min.time().replace(hour=lunch_end_hour, minute=lunch_end_minute)
            
            if lunch_start <= meeting_dt.time() < lunch_end:
                messages = self.rules.get('messages', {})
                suggestion = messages.get('lunch_time', '').format(
                    start=lunch_break.get('start_time'),
                    end=lunch_break.get('end_time')
                )
                issues.append("Время обеденного перерыва")
                return False, issues, suggestion
        
        return True, [], None
    
    def get_available_slots(self, date_str: str) -> List[str]:
        preferred_times = self.rules.get('special_rules', {}).get('preferred_times', [])
        
        available = []
        for time_str in preferred_times:
            is_valid, _, _ = self.validate_meeting_time(date_str, time_str)
            if is_valid:
                available.append(time_str)
        
        return available


_validator: Optional[MeetingValidator] = None


def get_meeting_validator() -> MeetingValidator:
    global _validator
    if _validator is None:
        _validator = MeetingValidator()
    return _validator
