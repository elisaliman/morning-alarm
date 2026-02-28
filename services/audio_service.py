from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from elevenlabs import AsyncElevenLabs
from elevenlabs.types import VoiceSettings
from pydub import AudioSegment

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_FORMAT = "mp3_44100_128"
SFX_DURATION = 2.0
INLINE_SFX_VOLUME_DB = -50
MUSIC_PROMPT = "calm ambient spa music, soft piano and gentle pads, peaceful and meditative"
MUSIC_TARGET_DBFS = -60
WEATHER_AMBIENCE_TARGET_DBFS = -60

_SPRING_BASE = "birds chirping softly in a garden, gentle morning breeze through leaves"

WEATHER_AMBIENCE_MAP = {
    "clear sky": f"{_SPRING_BASE}, warm sunlight ambience",
    "mainly clear": f"{_SPRING_BASE}, light breeze",
    "partly cloudy": f"{_SPRING_BASE}, soft wind through trees",
    "overcast": f"{_SPRING_BASE}, muted overcast sky, still air",
    "foggy": f"{_SPRING_BASE}, muffled foggy morning, damp air",
    "depositing rime fog": f"{_SPRING_BASE}, muffled fog, soft dripping",
    "light drizzle": f"{_SPRING_BASE}, gentle drizzle on leaves",
    "moderate drizzle": f"{_SPRING_BASE}, steady drizzle, rain on a window",
    "dense drizzle": f"{_SPRING_BASE}, steady rain falling on a rooftop",
    "slight rain": f"{_SPRING_BASE}, soft rain falling on leaves",
    "moderate rain": f"{_SPRING_BASE}, steady rain, raindrops on a rooftop",
    "heavy rain": f"{_SPRING_BASE}, heavy rain pouring, rain on a tin roof",
    "slight snow": f"{_SPRING_BASE}, quiet snowfall, soft winter wind",
    "moderate snow": f"{_SPRING_BASE}, snow falling softly",
    "heavy snow": f"{_SPRING_BASE}, heavy snowfall, howling wind",
    "slight rain showers": f"{_SPRING_BASE}, brief rain shower on leaves",
    "moderate rain showers": f"{_SPRING_BASE}, rain shower on a window",
    "violent rain showers": f"{_SPRING_BASE}, intense rain shower, downpour",
    "thunderstorm": f"{_SPRING_BASE}, distant rumbling thunder, rain",
    "thunderstorm with slight hail": f"{_SPRING_BASE}, thunder and light hail",
    "thunderstorm with heavy hail": f"{_SPRING_BASE}, heavy thunder, hailstorm",
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


async def _collect_stream(async_iter) -> bytes:
    """Drain an async byte-chunk iterator into a single bytes object."""
    chunks: list[bytes] = []
    async for chunk in async_iter:
        chunks.append(chunk)
    return b"".join(chunks)


async def _generate_tts(text: str) -> bytes:
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    return await _collect_stream(
        _client().text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format=AUDIO_FORMAT,
            voice_settings=VoiceSettings(
                stability=0.75,
                similarity_boost=0.5,
                style=0.1,
                speed=1.2,
            ),
        )
    )


async def _generate_sfx(description: str, duration: float = SFX_DURATION) -> bytes:
    return await _collect_stream(
        _client().text_to_sound_effects.convert(
            text=description,
            duration_seconds=min(duration, 22.0),
            output_format=AUDIO_FORMAT,
        )
    )


async def _generate_segment(segment: Segment) -> bytes:
    if segment.kind == "sfx":
        return await _generate_sfx(segment.content)
    return await _generate_tts(segment.content)


def _stitch(segments: list[Segment], audio_chunks: list[bytes]) -> AudioSegment:
    """Concatenate MP3 byte chunks, lowering inline SFX volume."""
    combined = AudioSegment.empty()
    for seg_meta, raw in zip(segments, audio_chunks):
        audio = AudioSegment.from_mp3(io.BytesIO(raw))
        if seg_meta.kind == "sfx":
            audio = audio + INLINE_SFX_VOLUME_DB
        combined += audio
    return combined


def _prepare_layer(raw: bytes, target_length: int, target_dbfs: float) -> AudioSegment:
    """Load an MP3, normalize to target dBFS, loop to fill target length, and fade."""
    layer = AudioSegment.from_mp3(io.BytesIO(raw))
    logger.info("Layer raw: %dms, dBFS=%.1f", len(layer), layer.dBFS)
    if layer.dBFS > -80:
        layer = layer.apply_gain(target_dbfs - layer.dBFS)
    if len(layer) < target_length:
        loops_needed = (target_length // len(layer)) + 1
        layer = layer * loops_needed
    layer = layer[:target_length]
    return layer.fade_in(2000).fade_out(3000)


def _mix_layers(foreground: AudioSegment, music_bytes: bytes, ambience_bytes: bytes) -> AudioSegment:
    """Overlay music and weather ambience underneath the foreground voice."""
    music = _prepare_layer(music_bytes, len(foreground), MUSIC_TARGET_DBFS)
    ambience = _prepare_layer(ambience_bytes, len(foreground), WEATHER_AMBIENCE_TARGET_DBFS)
    return foreground.overlay(music).overlay(ambience)


def _weather_ambience_prompt(weather_description: str) -> str:
    """Map the weather description to an appropriate ambience SFX prompt."""
    desc = weather_description.lower().strip()

    if desc in WEATHER_AMBIENCE_MAP:
        return WEATHER_AMBIENCE_MAP[desc]

    if "rain" in desc or "drizzle" in desc or "shower" in desc:
        return f"{_SPRING_BASE}, soft rain falling steadily"
    if "snow" in desc:
        return f"{_SPRING_BASE}, quiet snowfall, soft winter wind"
    if "thunder" in desc or "storm" in desc:
        return f"{_SPRING_BASE}, distant rumbling thunder, rain"
    if "fog" in desc:
        return f"{_SPRING_BASE}, muffled foggy morning"
    if "cloud" in desc or "overcast" in desc:
        return f"{_SPRING_BASE}, soft wind through trees"
    if "clear" in desc or "sunny" in desc:
        return f"{_SPRING_BASE}, warm sunlight ambience"

    return f"{_SPRING_BASE}"


async def generate_audio(script: str, weather_description: str = "") -> Path:
    """Parse script, generate all audio segments + backing layers, stitch, and return the MP3 path."""
    segments = parse_script(script)
    if not segments:
        raise ValueError("Script produced no audio segments")

    ambience_prompt = _weather_ambience_prompt(weather_description)
    logger.info("Weather: %r → ambience prompt: %r", weather_description, ambience_prompt)

    segment_tasks = [_generate_segment(seg) for seg in segments]
    music_task = _generate_sfx(MUSIC_PROMPT, 22.0)
    ambience_task = _generate_sfx(ambience_prompt, 22.0)

    results = await asyncio.gather(*segment_tasks, music_task, ambience_task)
    audio_chunks = list(results[:-2])
    music_bytes = results[-2]
    ambience_bytes = results[-1]

    logger.info(
        "Audio sizes — segments: %s, music: %d bytes, ambience: %d bytes",
        [len(c) for c in audio_chunks],
        len(music_bytes),
        len(ambience_bytes),
    )

    foreground = _stitch(segments, audio_chunks)
    combined = _mix_layers(foreground, music_bytes, ambience_bytes)

    filename = f"morning_{uuid.uuid4().hex[:8]}.mp3"
    out_path = OUTPUT_DIR / filename
    combined.export(str(out_path), format="mp3", bitrate="128k")

    return out_path
