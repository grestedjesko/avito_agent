import datetime as dt
import json
import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    def __init__(self, credentials_file: str = "credentials.json",
                 scopes: List[str] = None):
        self.credentials_file = credentials_file
        self.scopes = scopes or ["https://www.googleapis.com/auth/calendar"]

        with open(credentials_file, "r") as f:
            self.client_config = json.load(f)

    def get_auth_url(self, redirect_uri: str, state: str = None) -> str:
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.scopes,
            redirect_uri=redirect_uri,
            state=state
        )

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )

        return auth_url

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, str]:
        try:
            flow = Flow.from_client_config(
                self.client_config,
                scopes=self.scopes,
                redirect_uri=redirect_uri
            )

            flow.fetch_token(code=code)
            creds = flow.credentials

            if not creds or not creds.token:
                raise ValueError("Failed to obtain tokens")

            return {
                'access_token': creds.token,
                'refresh_token': creds.refresh_token
            }
        except Exception as e:
            logger.error(f"OAuth token exchange failed: {str(e)}")
            raise 

    def _build_service(self, refresh_token: str):
        client_info = (self.client_config.get("installed") or
                       self.client_config.get("web"))

        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=self.scopes
        )

        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def create_event(self, refresh_token: str,
                     summary: str,
                     start: dt.datetime,
                     end: dt.datetime,
                     description: str = None,
                     location: str = None,
                     calendar_id: str = "primary",
                     timezone: str = "Europe/Moscow") -> Optional[dict[str, Any]]:
        try:
            service = self._build_service(refresh_token)

            event_body = {
                "summary": summary,
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": timezone
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": timezone
                }
            }

            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location

            event = service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()

            logger.info(f"Событие создано: {event['id']}")
            return {"id": event["id"],
                    "htmlLink": event["htmlLink"]}

        except HttpError as e:
            logger.error(f"Ошибка создания события: {e}")
            return None

    def get_events(self, refresh_token: str,
                   time_min: dt.datetime = None,
                   time_max: dt.datetime = None,
                   max_results: int = 10,
                   calendar_id: str = "primary") -> List[Dict]:
        try:
            service = self._build_service(refresh_token)

            params = {
                'calendarId': calendar_id,
                'maxResults': max_results,
                'singleEvents': True,
                'orderBy': 'startTime'
            }

            if time_min:
                params['timeMin'] = time_min.isoformat()
            if time_max:
                params['timeMax'] = time_max.isoformat()

            events_result = service.events().list(**params).execute()
            events = events_result.get('items', [])

            return events

        except HttpError as e:
            logger.error(f"Ошибка получения событий: {e}")
            return []

    def update_event(self, refresh_token: str,
                     event_id: str,
                     summary: str = None,
                     start: dt.datetime = None,
                     end: dt.datetime = None,
                     description: str = None,
                     location: str = None,
                     calendar_id: str = "primary",
                     timezone: str = "Europe/Moscow") -> bool:
        try:
            service = self._build_service(refresh_token)

            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            if summary is not None:
                event['summary'] = summary
            if start is not None:
                event['start'] = {
                    'dateTime': start.isoformat(),
                    'timeZone': timezone
                }
            if end is not None:
                event['end'] = {
                    'dateTime': end.isoformat(),
                    'timeZone': timezone
                }
            if description is not None:
                event['description'] = description
            if location is not None:
                event['location'] = location

            service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()

            logger.info(f"Событие обновлено: {event_id}")
            return True

        except HttpError as e:
            logger.error(f"Ошибка обновления события: {e}")
            return False

    def delete_event(self, refresh_token: str,
                     event_id: str,
                     calendar_id: str = "primary") -> bool:
        try:
            service = self._build_service(refresh_token)

            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            logger.info(f"Событие удалено: {event_id}")
            return True

        except HttpError as e:
            logger.error(f"Ошибка удаления события: {e}")
            return False

    def get_calendars(self, refresh_token: str) -> List[Dict]:
        try:
            service = self._build_service(refresh_token)

            calendars_result = service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])

            return calendars

        except HttpError as e:
            logger.error(f"Ошибка получения календарей: {e}")
            return []

    def check_token_validity(self, refresh_token: str) -> bool:
        try:
            service = self._build_service(refresh_token)
            service.calendarList().list(maxResults=1).execute()
            return True
        except HttpError:
            return False


    def get_event(self, refresh_token: str, event_id: str, calendar_id: str = "primary") -> Optional[Dict[str, Any]]:
        try:
            service = self._build_service(refresh_token)
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            logger.info(f"Событие получено: {event_id}")
            return event

        except HttpError as e:
            logger.error(f"Ошибка получения события: {e}")
            return None