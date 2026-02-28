from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


@dataclass
class CalendarEvent:
    summary: str
    start: str
    end: str


def _get_credentials() -> Credentials:
    """Load or refresh Google OAuth credentials, prompting login if needed."""
    creds: Credentials | None = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"Missing {CREDENTIALS_FILE}. Download it from the Google Cloud Console "
                "and place it in the project root."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json())
    return creds


def _get_user_email(creds: Credentials) -> str:
    """Fetch the email address for the given credentials."""
    try:
        service = build("oauth2", "v2", credentials=creds)
        user_info = service.userinfo().get().execute()
        return user_info.get("email", "Unknown")
    except Exception:
        return "(could not fetch email)"


def fetch_todays_events() -> list[CalendarEvent]:
    """Return today's calendar events (synchronous — Google client is not async)."""
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    local_now = datetime.datetime.now().astimezone()
    start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = local_now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events: list[CalendarEvent] = []
    for item in result.get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date", ""))
        end = item["end"].get("dateTime", item["end"].get("date", ""))
        events.append(
            CalendarEvent(
                summary=item.get("summary", "(no title)"),
                start=start,
                end=end,
            )
        )
    return events


def fetch_todays_events_safe() -> list[CalendarEvent]:
    """Wrapper that returns an empty list on failure for demo resilience."""
    try:
        return fetch_todays_events()
    except Exception:
        return []


def get_connected_account() -> dict:
    """Return info about the connected Google account, or empty if not connected."""
    if not TOKEN_FILE.exists():
        return {"connected": False, "email": None}
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return {"connected": True, "email": _get_user_email(creds)}
    except Exception:
        return {"connected": True, "email": "(saved but could not fetch email)"}


def disconnect_account() -> None:
    """Remove the stored OAuth token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def reconnect_account() -> str:
    """Force a fresh OAuth flow and return the connected email."""
    disconnect_account()
    creds = _get_credentials()
    return _get_user_email(creds)
