import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, time
from dateutil import parser
from config import get_settings
from .calendar_client import GoogleCalendarClient

logger = logging.getLogger(__name__)


class TimeInterval:
    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end
    
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)
    
    def overlaps_with(self, other: 'TimeInterval') -> bool:
        return not (self.end <= other.start or self.start >= other.end)
    
    def __repr__(self):
        return f"TimeInterval({self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')})"


class CalendarService:
    DEFAULT_MEETING_DURATION = 30
    MIN_INTERVAL_STEP = 15
    DEFAULT_TIMEZONE = "Europe/Moscow"
    
    def __init__(self, refresh_token: Optional[str] = None):
        settings = get_settings()
        self.credentials_file = settings.google_calendar_credentials_file
        self.calendar_id = settings.google_calendar_id or "primary"
        self.refresh_token = refresh_token or settings.google_calendar_refresh_token
        self.timezone = self.DEFAULT_TIMEZONE
        
        try:
            self.client = GoogleCalendarClient(credentials_file=self.credentials_file)
            self.enabled = bool(self.refresh_token)
            logger.info(f"Calendar service initialized (enabled={self.enabled})")
        except Exception as e:
            logger.warning(f"Failed to initialize calendar client: {e}")
            self.client = None
            self.enabled = False
    
    def set_refresh_token(self, refresh_token: str):
        self.refresh_token = refresh_token
        self.enabled = bool(refresh_token)
        logger.info("Refresh token updated")
    
    def is_enabled(self) -> bool:
        return self.enabled and self.client is not None and self.refresh_token is not None
    
    def check_availability(
        self,
        date_str: str,
        time_str: str,
        duration_minutes: int = DEFAULT_MEETING_DURATION
    ) -> bool:
        if not self.is_enabled():
            logger.warning("Calendar service is not enabled")
            return False
        
        try:
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            events = self.client.get_events(
                refresh_token=self.refresh_token,
                time_min=start_dt,
                time_max=end_dt,
                calendar_id=self.calendar_id
            )
            
            requested_interval = TimeInterval(start_dt, end_dt)
            
            for event in events:
                event_start = parser.isoparse(event['start'].get('dateTime', event['start'].get('date')))
                event_end = parser.isoparse(event['end'].get('dateTime', event['end'].get('date')))
                event_interval = TimeInterval(event_start, event_end)
                
                if requested_interval.overlaps_with(event_interval):
                    logger.info(f"Interval {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} overlaps with event: {event.get('summary', 'Unnamed')}")
                    return False
            
            logger.info(f"Interval {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} is available")
            return True
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return False
    
    def create_event(
        self,
        title: str,
        location: str,
        date_str: str,
        time_str: str,
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled():
            logger.warning("Calendar service is not enabled")
            return None
        
        try:
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            event_description = description or f"Встреча в {location}"
            
            result = self.client.create_event(
                refresh_token=self.refresh_token,
                summary=title,
                start=start_dt,
                end=end_dt,
                description=event_description,
                location=location,
                calendar_id=self.calendar_id,
                timezone=self.timezone
            )
            
            if result:
                logger.info(f"Event created: {title} on {date_str} at {time_str}")
                return {
                    "id": result["id"],
                    "title": title,
                    "location": location,
                    "date": date_str,
                    "time": time_str,
                    "duration": duration_minutes,
                    "description": event_description,
                    "link": result.get("htmlLink")
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return None
    
    def get_free_intervals(
        self,
        date_str: str,
        business_hours: Tuple[int, int] = (9, 18),
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        step_minutes: int = MIN_INTERVAL_STEP
    ) -> List[str]:
        if not self.is_enabled():
            logger.warning("Calendar service is not enabled")
            return []
        
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            start_hour, end_hour = business_hours
            day_start = datetime.combine(target_date, time(start_hour, 0))
            day_end = datetime.combine(target_date, time(end_hour, 0))
            
            events = self.client.get_events(
                refresh_token=self.refresh_token,
                time_min=day_start,
                time_max=day_end,
                max_results=100,
                calendar_id=self.calendar_id
            )
            
            busy_intervals = []
            for event in events:
                try:
                    event_start = parser.isoparse(event['start'].get('dateTime', event['start'].get('date')))
                    event_end = parser.isoparse(event['end'].get('dateTime', event['end'].get('date')))
                    busy_intervals.append(TimeInterval(event_start, event_end))
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")
                    continue
            
            free_start_times = []
            current_time = day_start
            
            while current_time + timedelta(minutes=duration_minutes) <= day_end:
                candidate_interval = TimeInterval(
                    current_time,
                    current_time + timedelta(minutes=duration_minutes)
                )
                
                is_free = True
                for busy_interval in busy_intervals:
                    if candidate_interval.overlaps_with(busy_interval):
                        is_free = False
                        current_time = busy_interval.end
                        break
                
                if is_free:
                    free_start_times.append(current_time.strftime("%H:%M"))
                    current_time += timedelta(minutes=step_minutes)
            
            logger.info(f"Found {len(free_start_times)} free intervals for {date_str}")
            return free_start_times
            
        except Exception as e:
            logger.error(f"Error getting free intervals: {e}")
            return []
    
    def get_next_available_interval(
        self,
        start_date_str: str,
        days_ahead: int = 7,
        business_hours: Tuple[int, int] = (9, 18),
        duration_minutes: int = DEFAULT_MEETING_DURATION
    ) -> Optional[Dict[str, str]]:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            
            for day_offset in range(days_ahead):
                check_date = start_date + timedelta(days=day_offset)
                date_str = check_date.strftime("%Y-%m-%d")
                
                free_intervals = self.get_free_intervals(
                    date_str=date_str,
                    business_hours=business_hours,
                    duration_minutes=duration_minutes
                )
                
                if free_intervals:
                    return {
                        "date": date_str,
                        "time": free_intervals[0]
                    }
            
            logger.warning(f"No available intervals found in next {days_ahead} days")
            return None
            
        except Exception as e:
            logger.error(f"Error finding next available interval: {e}")
            return None
    
    def cancel_event(self, event_id: str) -> bool:
        if not self.is_enabled():
            logger.warning("Calendar service is not enabled")
            return False
        
        try:
            success = self.client.delete_event(
                refresh_token=self.refresh_token,
                event_id=event_id,
                calendar_id=self.calendar_id
            )
            
            if success:
                logger.info(f"Event cancelled: {event_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error cancelling event: {e}")
            return False
    
    def update_event(
        self,
        event_id: str,
        **updates
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled():
            logger.warning("Calendar service is not enabled")
            return None
        
        try:
            summary = None
            location = None
            description = None
            start_dt = None
            end_dt = None
            
            if 'title' in updates:
                summary = updates['title']
            
            if 'location' in updates:
                location = updates['location']
            
            if 'description' in updates:
                description = updates['description']
            
            if 'date_str' in updates and 'time_str' in updates:
                start_dt = datetime.strptime(
                    f"{updates['date_str']} {updates['time_str']}",
                    "%Y-%m-%d %H:%M"
                )
                duration = updates.get('duration_minutes', self.DEFAULT_MEETING_DURATION)
                end_dt = start_dt + timedelta(minutes=duration)
            
            success = self.client.update_event(
                refresh_token=self.refresh_token,
                event_id=event_id,
                summary=summary,
                start=start_dt,
                end=end_dt,
                description=description,
                location=location,
                calendar_id=self.calendar_id,
                timezone=self.timezone
            )
            
            if success:
                logger.info(f"Event updated: {event_id}")
                return {"id": event_id, **updates}
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return None


_calendar_service: Optional[CalendarService] = None


def get_calendar_service(refresh_token: Optional[str] = None) -> CalendarService:
    global _calendar_service
    if refresh_token is None:
        settings = get_settings()
        refresh_token = settings.google_calendar_refresh_token
    
    if _calendar_service is None:
        _calendar_service = CalendarService(refresh_token=refresh_token)
    elif refresh_token:
        _calendar_service.set_refresh_token(refresh_token)
    return _calendar_service
