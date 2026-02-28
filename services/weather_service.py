from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

WMO_DESCRIPTIONS = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


@dataclass
class WeatherReport:
    temp_f: float
    feels_like_f: float
    description: str
    humidity: int
    wind_mph: float

    def summary(self) -> str:
        return (
            f"{self.temp_f:.0f}°F (feels like {self.feels_like_f:.0f}°F), "
            f"{self.description}, humidity {self.humidity}%, "
            f"wind {self.wind_mph:.0f} mph"
        )


async def fetch_weather() -> WeatherReport:
    """Fetch current weather from Open-Meteo (free, no API key needed)."""
    lat = os.getenv("WEATHER_LAT", "40.7128")
    lon = os.getenv("WEATHER_LON", "-74.0060")

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data["current"]
    weather_code = current.get("weather_code", 0)

    return WeatherReport(
        temp_f=current["temperature_2m"],
        feels_like_f=current["apparent_temperature"],
        description=WMO_DESCRIPTIONS.get(weather_code, "unknown conditions"),
        humidity=current["relative_humidity_2m"],
        wind_mph=current["wind_speed_10m"],
    )
