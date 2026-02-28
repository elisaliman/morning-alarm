from __future__ import annotations

import os

from google import genai

from services.calendar_service import CalendarEvent
from services.weather_service import WeatherReport

SYSTEM_PROMPT = """\
You are a gentle morning wellness guide. Your voice is calm, warm, and \
unhurried — like a spa receptionist crossed with a meditation teacher. \
Your job is to ease ONE listener into their day with a soothing 45-second \
morning announcement.

Rules:
- Speak slowly and softly. Use short, breathing-room sentences.
- Gently weave the weather and calendar into the flow. Frame events as \
invitations, not obligations ("You have a lovely meeting at ten" not \
"You have a meeting at 10 AM").
- Insert 2 to 3 short transitional sound-effect tags to punctuate the script. \
Use the format [sfx:description] where description is a brief, specific sound \
(e.g. [sfx:single deep bell chime], [sfx:a slow deep breath exhale], \
[sfx:one soft gong hit]).
- Each sfx tag must appear on its own line, between spoken paragraphs.
- These should be short punctuation sounds (1-3 seconds), NOT ambient backgrounds. \
Do NOT use birds, rain, wind, or nature loops — those are handled separately.
- Space the sfx tags out evenly — one near the start, one in the middle, and \
optionally one near the end.
- Keep it under 100 words of spoken text (excluding sfx tags).
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
