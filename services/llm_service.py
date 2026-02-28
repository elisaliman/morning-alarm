from __future__ import annotations

import os
from datetime import datetime

from google import genai

from services.calendar_service import CalendarEvent
from services.weather_service import WeatherReport

SYSTEM_PROMPT = """\
You are a calm, friendly morning briefing voice. Think of a thoughtful \
friend who gently catches you up on your day while you're still waking up. \
Rules:
- Keep the tone relaxed and conversational. No flowery or spiritual language. \
No "dear one", "beloved", "take a breath", or "embrace the day".
- Mention the weather naturally, like you'd tell a friend ("It's 55 and cloudy \
out there, so maybe grab a jacket").
- You MUST mention EVERY calendar event provided — do not skip any. For each \
one, always say what it is and what time it starts. Say the time naturally \
("You've got a standup at nine", "Lunch with Sarah is at noon", \
"and dinner at nine tonight").
- If there are no events, mention it briefly and positively.
- Insert 2 to 3 short transitional sound-effect tags to punctuate the script. \
Use the format [sfx:description] where description is a calm, organic sound \
(e.g. [sfx:a single tibetan singing bowl ring], [sfx:a soft wooden wind chime], \
[sfx:a gentle tap on a ceramic bowl]). Think spa, yoga studio, zen garden — \
NOT digital chimes, UI sounds, or notification dings.
- Each sfx tag must appear on its own line, between spoken paragraphs.
- Space the sfx tags out evenly through the script.
- Keep it under 150 words of spoken text (excluding sfx tags). Longer is fine \
if needed to cover all events.
- Do NOT use hashtags, emojis, or markdown. Output plain text only.
"""


def _format_time(iso_str: str) -> str:
    """Convert an ISO datetime string to a human-readable time like '10:00 AM'."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%-I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return iso_str


def _build_user_message(weather: WeatherReport, events: list[CalendarEvent]) -> str:
    lines = [f"Weather right now: {weather.summary()}"]

    if events:
        lines.append("Today's schedule:")
        for e in events:
            start = _format_time(e.start)
            end = _format_time(e.end)
            lines.append(f"  - {e.summary} at {start} (until {end})")
    else:
        lines.append("Schedule: Nothing on the calendar today.")

    return "\n".join(lines)


async def generate_script(
    weather: WeatherReport,
    events: list[CalendarEvent],
) -> str:
    """Call Gemini to produce the morning radio script."""
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    user_msg = _build_user_message(weather, events)

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\n{user_msg}",
        config=genai.types.GenerateContentConfig(
            temperature=0.9,
            max_output_tokens=1024,
            thinking_config=genai.types.ThinkingConfig(
                thinking_budget=0,
            ),
        ),
    )

    return response.text or ""
