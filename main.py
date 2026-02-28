from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from services.audio_service import generate_audio
from services.calendar_service import (
    disconnect_account,
    fetch_todays_events_safe,
    get_connected_account,
    reconnect_account,
)
from services.llm_service import generate_script
from services.weather_service import fetch_weather

app = FastAPI(title="Morning Alarm")

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "audio").mkdir(exist_ok=True)

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"

DEFAULT_SETTINGS = {
    "location": {"lat": "40.7128", "lon": "-74.0060", "name": "New York"},
}


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return dict(DEFAULT_SETTINGS)


def _save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


# --- API ---


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class LocationUpdate(BaseModel):
    lat: str
    lon: str
    name: str = ""


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/cities")
async def search_cities(q: str = ""):
    """Proxy Open-Meteo geocoding to find cities by name."""
    if len(q.strip()) < 2:
        return {"results": []}
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(GEOCODE_URL, params={
            "name": q,
            "count": 8,
            "language": "en",
            "format": "json",
        })
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("results", []):
        label = r.get("name", "")
        admin = r.get("admin1", "")
        country = r.get("country", "")
        if admin:
            label += f", {admin}"
        if country:
            label += f", {country}"
        results.append({
            "label": label,
            "lat": str(r["latitude"]),
            "lon": str(r["longitude"]),
        })
    return {"results": results}


@app.get("/api/settings")
async def get_settings():
    settings = _load_settings()
    google = await asyncio.to_thread(get_connected_account)
    return {
        "location": settings.get("location", DEFAULT_SETTINGS["location"]),
        "google": google,
    }


@app.put("/api/settings/location")
async def update_location(body: LocationUpdate):
    settings = _load_settings()
    settings["location"] = {"lat": body.lat, "lon": body.lon, "name": body.name}
    _save_settings(settings)
    return {"ok": True, "location": settings["location"]}


@app.post("/api/google/disconnect")
async def google_disconnect():
    await asyncio.to_thread(disconnect_account)
    return {"ok": True}


@app.post("/api/google/connect")
async def google_connect():
    try:
        email = await asyncio.to_thread(reconnect_account)
        return {"ok": True, "email": email}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


_daily_cache: dict[str, dict] = {}


@app.get("/generate-morning")
async def generate_morning():
    today = date.today().isoformat()

    if today in _daily_cache:
        logger.info("Serving cached morning for %s", today)
        return _daily_cache[today]

    try:
        settings = _load_settings()
        loc = settings.get("location", DEFAULT_SETTINGS["location"])

        weather, events = await asyncio.gather(
            fetch_weather(lat=loc["lat"], lon=loc["lon"]),
            asyncio.to_thread(fetch_todays_events_safe),
        )

        script = await generate_script(weather, events)
        audio_path = await generate_audio(script, weather.description)

        result = {
            "script": script,
            "audio_url": f"/static/audio/{audio_path.name}",
        }

        _daily_cache.clear()
        _daily_cache[today] = result
        logger.info("Generated and cached morning for %s", today)

        return result

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/cache/clear")
async def clear_cache():
    _daily_cache.clear()
    logger.info("Daily cache cleared manually")
    return {"ok": True}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
