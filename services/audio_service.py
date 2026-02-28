from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from elevenlabs import AsyncElevenLabs
from pydub import AudioSegment

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_FORMAT = "mp3_44100_128"
SFX_DURATION = 2.0
INLINE_SFX_VOLUME_DB = -10
MUSIC_PROMPT = "calm ambient spa music, soft piano and gentle pads, peaceful and meditative"
MUSIC_VOLUME_DB = -18
WEATHER_AMBIENCE_VOLUME_DB = -14  # weather sounds slightly louder than music

WEATHER_AMBIENCE_MAP = {
    "clear sky": "quiet morning outdoors, gentle birdsong, light breeze",
    "mainly clear": "calm morning birdsong with a soft breeze",
    "partly cloudy": "soft wind through trees, occasional birdsong",
    "overcast": "muted wind, distant soft ambience, overcast morning",
    "foggy": "muffled foggy morning, distant fog horn, still air",
    "depositing rime fog": "muffled foggy morning, still air, soft dripping",
    "light drizzle": "gentle light drizzle on leaves, soft rain",
    "moderate drizzle": "steady drizzle, rain on a window",
    "dense drizzle": "steady rain falling, drizzle on a rooftop",
    "slight rain": "soft rain falling, rain on a window",
    "moderate rain": "steady rain, raindrops on a rooftop",
    "heavy rain": "heavy rain pouring, rain on a tin roof",
    "slight snow": "quiet snowfall, soft winter wind",
    "moderate snow": "snow falling softly, gentle winter breeze",
    "heavy snow": "heavy snowfall, howling winter wind",
    "slight rain showers": "brief rain shower, raindrops on leaves",
    "moderate rain showers": "rain shower, rain on a window",
    "violent rain showers": "intense rain shower, heavy downpour",
    "thunderstorm": "distant rumbling thunder, rain",
    "thunderstorm with slight hail": "thunder and light hail on a rooftop",
    "thunderstorm with heavy hail": "heavy thunder, hailstorm on a roof",
}

_SFX_PATTERN = re.compile(r"\[sfx:([^\]]+)\]", re.IGNORECASE)


@dataclass
class Segment:
    kind: str  # "text" or "sfx"
    content: str


def parse_script(script: str) -> list[Segment]:
    """Split an LLM script into ordered text and sfx segments."""
    segments: list[Segment] = []
    last_end = 0

    for match in _SFX_PATTERN.finditer(script):
        text_before = script[last_end : match.start()].strip()
        if text_before:
            segments.append(Segment(kind="text", content=text_before))
        segments.append(Segment(kind="sfx", content=match.group(1).strip()))
        last_end = match.end()

    trailing = script[last_end:].strip()
    if trailing:
        segments.append(Segment(kind="text", content=trailing))

    return segments


def _client() -> AsyncElevenLabs:
    return AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY", ""))


async def _generate_tts(text: str) -> bytes:
    client = _client()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    chunks: list[bytes] = []
    async for chunk in client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format=AUDIO_FORMAT,
    ):
        chunks.append(chunk)
    return b"".join(chunks)


async def _generate_sfx(description: str) -> bytes:
    client = _client()
    chunks: list[bytes] = []
    async for chunk in client.text_to_sound_effects.convert(
        text=description,
        duration_seconds=SFX_DURATION,
        output_format=AUDIO_FORMAT,
    ):
        chunks.append(chunk)
    return b"".join(chunks)


async def _generate_segment(segment: Segment) -> bytes:
    if segment.kind == "sfx":
        return await _generate_sfx(segment.content)
    return await _generate_tts(segment.content)


async def _generate_sfx_track(prompt: str, duration_seconds: float) -> bytes:
    """Generate an SFX track from a text prompt."""
    client = _client()
    chunks: list[bytes] = []
    async for chunk in client.text_to_sound_effects.convert(
        text=prompt,
        duration_seconds=min(duration_seconds, 22.0),  # ElevenLabs SFX max is 22s
        output_format=AUDIO_FORMAT,
    ):
        chunks.append(chunk)
    return b"".join(chunks)


def _stitch(segments: list[Segment], audio_chunks: list[bytes]) -> AudioSegment:
    """Concatenate MP3 byte chunks, lowering inline SFX volume."""
    combined = AudioSegment.empty()
    for seg_meta, raw in zip(segments, audio_chunks):
        audio = AudioSegment.from_mp3(io.BytesIO(raw))
        if seg_meta.kind == "sfx":
            audio = audio + INLINE_SFX_VOLUME_DB
        combined += audio
    return combined


def _prepare_layer(raw: bytes, target_length: int, volume_db: float) -> AudioSegment:
    """Load an MP3, adjust volume, loop to fill target length, and fade."""
    layer = AudioSegment.from_mp3(io.BytesIO(raw)) + volume_db
    if len(layer) < target_length:
        loops_needed = (target_length // len(layer)) + 1
        layer = layer * loops_needed
    layer = layer[:target_length]
    return layer.fade_in(2000).fade_out(3000)


def _mix_layers(foreground: AudioSegment, music_bytes: bytes, ambience_bytes: bytes) -> AudioSegment:
    """Overlay music and weather ambience underneath the foreground voice."""
    music = _prepare_layer(music_bytes, len(foreground), MUSIC_VOLUME_DB)
    ambience = _prepare_layer(ambience_bytes, len(foreground), WEATHER_AMBIENCE_VOLUME_DB)
    return foreground.overlay(music).overlay(ambience)


def _weather_ambience_prompt(weather_description: str) -> str:
    """Map the weather description to an appropriate ambience SFX prompt."""
    desc = weather_description.lower().strip()

    if desc in WEATHER_AMBIENCE_MAP:
        return WEATHER_AMBIENCE_MAP[desc]

    # Fuzzy keyword fallback
    if "rain" in desc or "drizzle" in desc or "shower" in desc:
        return "soft rain falling steadily, rain on a window"
    if "snow" in desc:
        return "quiet snowfall, soft winter wind"
    if "thunder" in desc or "storm" in desc:
        return "distant rumbling thunder, rain"
    if "fog" in desc:
        return "muffled foggy morning, still air"
    if "cloud" in desc or "overcast" in desc:
        return "soft wind through trees, muted morning"
    if "clear" in desc or "sunny" in desc:
        return "quiet morning outdoors, gentle birdsong, light breeze"

    return "calm outdoor morning ambience, gentle breeze"


async def generate_audio(script: str, weather_description: str = "") -> Path:
    """Parse script, generate all audio segments + backing layers, stitch, and return the MP3 path."""
    segments = parse_script(script)
    if not segments:
        raise ValueError("Script produced no audio segments")

    ambience_prompt = _weather_ambience_prompt(weather_description)

    # Generate all segments, music, and weather ambience concurrently
    segment_tasks = [_generate_segment(seg) for seg in segments]
    music_task = _generate_sfx_track(MUSIC_PROMPT, 22.0)
    ambience_task = _generate_sfx_track(ambience_prompt, 22.0)

    results = await asyncio.gather(*segment_tasks, music_task, ambience_task)
    audio_chunks = list(results[:-2])
    music_bytes = results[-2]
    ambience_bytes = results[-1]

    foreground = _stitch(segments, audio_chunks)
    combined = _mix_layers(foreground, music_bytes, ambience_bytes)

    filename = f"morning_{uuid.uuid4().hex[:8]}.mp3"
    out_path = OUTPUT_DIR / filename
    combined.export(str(out_path), format="mp3", bitrate="128k")

    return out_path
