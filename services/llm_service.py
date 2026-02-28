from __future__ import annotations

import os
from datetime import datetime

from google import genai

from services.calendar_service import CalendarEvent
from services.weather_service import WeatherReport

SYSTEM_PROMPT = """\
You are a calm, friendly morning briefing voice — like a thoughtful friend \
gently catching you up while you're still waking up.

Tone rules:
- Relaxed and conversational. No flowery or spiritual language.
- Never use: "dear one", "beloved", "take a breath", "embrace the day", \
or similar.

Weather rules:
- Include the temperature, feels-like, and conditions — but phrase it the \
way you'd actually say it to a friend, not like you're reading off a display.
- Good: "It's thirty-two degrees out but feels more like twenty-two, so bundle up"

Calendar rules:
- You MUST mention EVERY calendar event — do not skip any.
- For each event, always include what it is and the start time, spoken \
naturally ("You've got a standup at nine", "Lunch with Sarah is at noon").
- If there are no events, acknowledge it briefly and warmly.

Sound effect rules:
- Insert exactly 2 to 3 sound effect tags throughout the script using this \
format: [sfx:description]
- Each tag must be on its own line, between spoken paragraphs.
- Space them evenly — beginning, middle, and end of the script.
- Descriptions must be nature-related and grounded in the real world. Think \
things you would actually hear on a calm morning outdoors — organic, acoustic, \
from the natural environment. Never digital, synthetic, UI-sounding, or \
notification-like.
- Be specific and sensory in descriptions. Describe the actual sound, not a \
category or object name. Every sfx must be unique — never repeat the same one.
- Be creative. Invent something different every time. Do not fall back on the \
same sounds.

TTS optimization rules (IMPORTANT — these make the voice sound natural):
- Write ALL numbers and times as spoken words, not digits. \
"nine fifteen in the morning" not "9:15 AM". "fifty-five degrees" not "55°F".
- Add natural pauses between sections using the SSML tag <break time="1.0s" /> \
on its own line. Place one after the opening greeting, one before wrapping up. \
Do not use more than 3 break tags total.
- Use short sentences. One idea per sentence. This prevents the voice from \
rushing through long clauses.
- Use dashes for micro-pauses mid-sentence: "It's cloudy — but not too cold."

Format rules:
- Keep spoken text under 150 words. If needed to cover all events, \
go slightly over — completeness takes priority.
- No hashtags, emojis, or markdown. Plain text only.
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
        model="gemini-3-flash-preview",
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
