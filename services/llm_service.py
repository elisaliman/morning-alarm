from __future__ import annotations

import os

from google import genai

from services.calendar_service import CalendarEvent
from services.weather_service import WeatherReport

SYSTEM_PROMPT = """\
You are a gentle morning wellness guide. Your voice is calm, warm, and \
unhurried — like a spa receptionist crossed with a meditation teacher. \
Your job is to ease ONE listener into their day with a soothing 30-second \
morning announcement.

Rules:
- Speak slowly and softly. Use short, breathing-room sentences.
- Gently weave the weather and calendar into the flow. Frame events as \
invitations, not obligations ("You have a lovely meeting at ten" not \
"You have a meeting at 10 AM").
- Insert EXACTLY one sound-effect tag where it fits the mood. Use the format \
[sfx:description] where description is a short natural-language phrase \
(e.g. [sfx:gentle singing bowl], [sfx:soft rain and birdsong], \
[sfx:calm ocean waves]).
- The sfx tag must appear on its own line, between spoken paragraphs.
- Keep it under 80 words of spoken text (excluding the sfx tag).
- Do NOT use hashtags, emojis, or markdown. Output plain text only.
"""


def _build_user_message(weather: WeatherReport, events: list[CalendarEvent]) -> str:
    lines = [f"Weather right now: {weather.summary()}"]

    if events:
        lines.append("Today's calendar:")
        for e in events:
            lines.append(f"  - {e.summary} ({e.start} → {e.end})")
    else:
        lines.append("Calendar: Nothing scheduled today — a free day!")

    return "\n".join(lines)


async def generate_script(
    weather: WeatherReport,
    events: list[CalendarEvent],
) -> str:
    """Call Gemini to produce the morning radio script."""
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    user_msg = _build_user_message(weather, events)

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"{SYSTEM_PROMPT}\n\n{user_msg}",
        config=genai.types.GenerateContentConfig(
            temperature=0.9,
            max_output_tokens=300,
        ),
    )

    return response.text or ""
