"""
data_fetcher.py
---------------
Pulls all environmental data for the ReelAI forecast:
  - NOAA Tides & Currents (tide predictions)
  - NOAA NDBC buoys     (water temp, wave height, wind)
  - Open-Meteo          (wind forecast, no API key needed)
  - Moon phase          (astronomical calculation, no API needed)
"""

import math
import requests
from datetime import datetime, timezone, timedelta


# ── Station config (Cape Cod) ─────────────────────────────────────────────────
TIDE_STATION   = "8447930"   # Chatham, MA
BUOY_STATION   = "44020"     # Nantucket Sound (water temp, waves)
CAPE_COD_LAT   = 41.6688
CAPE_COD_LON   = -69.9634


# ── Tides ─────────────────────────────────────────────────────────────────────

def get_tides() -> dict:
    """
    Fetch today's tide predictions from NOAA Tides & Currents API.
    Returns tide stage, next high/low, and hours until next event.
    """
    today = datetime.now().strftime("%Y%m%d")
    url = (
        "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
        f"?begin_date={today}&end_date={today}"
        f"&station={TIDE_STATION}"
        "&product=predictions&datum=MLLW&time_zone=lst_ldt"
        "&interval=hilo&units=english&application=ReelAI&format=json"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        predictions = resp.json().get("predictions", [])

        now = datetime.now()
        upcoming = []
        for p in predictions:
            t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
            upcoming.append({"time": t, "type": p["type"], "height": float(p["v"])})

        # Find the most recent past event and next future event
        past   = [e for e in upcoming if e["time"] <= now]
        future = [e for e in upcoming if e["time"] >  now]

        last_event = past[-1]  if past   else None
        next_event = future[0] if future else None

        # Determine current tide stage (rising or falling)
        if last_event and next_event:
            stage = "rising" if next_event["type"] == "H" else "falling"
            hours_until_next = (next_event["time"] - now).seconds / 3600
        else:
            stage = "unknown"
            hours_until_next = None

        return {
            "stage": stage,
            "last_event_type": last_event["type"] if last_event else None,
            "last_event_time": last_event["time"].strftime("%I:%M %p") if last_event else None,
            "last_event_height": last_event["height"] if last_event else None,
            "next_event_type": next_event["type"] if next_event else None,
            "next_event_time": next_event["time"].strftime("%I:%M %p") if next_event else None,
            "next_event_height": next_event["height"] if next_event else None,
            "hours_until_next": round(hours_until_next, 1) if hours_until_next else None,
            "all_events": [
                {"time": e["time"].strftime("%I:%M %p"), "type": e["type"], "height": e["height"]}
                for e in upcoming
            ],
        }
    except Exception as e:
        return {"error": str(e), "stage": "unknown"}


# ── NOAA Buoy ─────────────────────────────────────────────────────────────────

def get_buoy_data() -> dict:
    """
    Fetch latest observation from NOAA NDBC buoy 44020 (Nantucket Sound).
    Returns water temp, wave height, wind speed/direction.
    """
    url = f"https://www.ndbc.noaa.gov/data/realtime2/{BUOY_STATION}.txt"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")

        # Line 0 = header names, line 1 = units, line 2+ = data (most recent first)
        headers = lines[0].lstrip("#").split()
        data_line = lines[2].split()  # Most recent observation

        row = dict(zip(headers, data_line))

        def safe_float(key):
            val = row.get(key, "MM")
            return float(val) if val not in ("MM", "N/A", "") else None

        water_temp_c = safe_float("WTMP")
        water_temp_f = round(water_temp_c * 9/5 + 32, 1) if water_temp_c is not None else None
        wave_height_m = safe_float("WVHT")
        wave_height_ft = round(wave_height_m * 3.281, 1) if wave_height_m is not None else None

        wind_speed_ms = safe_float("WSPD")
        wind_speed_mph = round(wind_speed_ms * 2.237, 1) if wind_speed_ms is not None else None
        wind_dir = safe_float("WDIR")

        def wind_direction_label(degrees):
            if degrees is None:
                return None
            dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                    "S","SSW","SW","WSW","W","WNW","NW","NNW"]
            idx = round(degrees / 22.5) % 16
            return dirs[idx]

        return {
            "water_temp_f": water_temp_f,
            "water_temp_c": round(water_temp_c, 1) if water_temp_c else None,
            "wave_height_ft": wave_height_ft,
            "wind_speed_mph": wind_speed_mph,
            "wind_direction_deg": wind_dir,
            "wind_direction_label": wind_direction_label(wind_dir),
            "observation_time": f"{row.get('YY','?')}-{row.get('MM','?')}-{row.get('DD','?')} {row.get('hh','?')}:{row.get('mm','?')} UTC",
            "buoy_station": BUOY_STATION,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Weather forecast ──────────────────────────────────────────────────────────

def get_weather() -> dict:
    """
    Fetch current weather and short forecast from Open-Meteo (free, no API key).
    Returns wind speed, gusts, precipitation, cloud cover.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={CAPE_COD_LAT}&longitude={CAPE_COD_LON}"
        "&current=wind_speed_10m,wind_gusts_10m,wind_direction_10m,"
        "precipitation,cloud_cover,weather_code"
        "&wind_speed_unit=mph&temperature_unit=fahrenheit"
        "&forecast_days=1&timezone=America/New_York"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        current = resp.json().get("current", {})

        def wind_direction_label(degrees):
            dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                    "S","SSW","SW","WSW","W","WNW","NW","NNW"]
            return dirs[round(degrees / 22.5) % 16]

        wind_dir = current.get("wind_direction_10m")

        # WMO weather code → human readable
        wmo_codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
            61: "Light rain", 63: "Rain", 65: "Heavy rain",
            71: "Light snow", 73: "Snow", 75: "Heavy snow",
            80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
            95: "Thunderstorm", 99: "Thunderstorm with hail",
        }
        weather_code = current.get("weather_code", 0)

        return {
            "wind_speed_mph": current.get("wind_speed_10m"),
            "wind_gusts_mph": current.get("wind_gusts_10m"),
            "wind_direction_deg": wind_dir,
            "wind_direction_label": wind_direction_label(wind_dir) if wind_dir else None,
            "precipitation_in": current.get("precipitation"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "conditions": wmo_codes.get(weather_code, "Unknown"),
            "weather_code": weather_code,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Moon phase ────────────────────────────────────────────────────────────────

def get_moon_phase() -> dict:
    """
    Calculate current moon phase using a simple astronomical formula.
    No API needed — pure math.
    """
    now = datetime.now(timezone.utc)
    # Known new moon reference: Jan 6, 2000 at 18:14 UTC
    known_new_moon = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    lunar_cycle_days = 29.53058867

    days_since = (now - known_new_moon).total_seconds() / 86400
    phase_days = days_since % lunar_cycle_days  # 0 = new moon, 14.77 = full moon

    # Phase name
    if phase_days < 1.85:
        phase_name = "New moon"
    elif phase_days < 7.38:
        phase_name = "Waxing crescent"
    elif phase_days < 9.22:
        phase_name = "First quarter"
    elif phase_days < 14.77:
        phase_name = "Waxing gibbous"
    elif phase_days < 16.61:
        phase_name = "Full moon"
    elif phase_days < 22.15:
        phase_name = "Waning gibbous"
    elif phase_days < 23.99:
        phase_name = "Last quarter"
    elif phase_days < 29.53:
        phase_name = "Waning crescent"
    else:
        phase_name = "New moon"

    # Illumination percentage (0 = new, 100 = full)
    illumination = round((1 - math.cos(2 * math.pi * phase_days / lunar_cycle_days)) / 2 * 100)

    # Fishing quality: best near new/full moon (solunar theory)
    days_from_new_or_full = min(phase_days, abs(phase_days - 14.77))
    solunar_score = max(0, 10 - days_from_new_or_full * 1.5)  # 0–10

    return {
        "phase_name": phase_name,
        "phase_days": round(phase_days, 1),
        "illumination_pct": illumination,
        "solunar_score": round(solunar_score, 1),
        "fishing_note": (
            "Excellent — near new/full moon" if solunar_score >= 8
            else "Good — active moon phase" if solunar_score >= 5
            else "Moderate moon influence"
        ),
    }


# ── Aggregate all data ────────────────────────────────────────────────────────

def get_all_conditions() -> dict:
    """Fetch all environmental data and return as a single dict."""
    print("Fetching tides...")
    tides = get_tides()
    print("Fetching buoy data...")
    buoy = get_buoy_data()
    print("Fetching weather...")
    weather = get_weather()
    print("Calculating moon phase...")
    moon = get_moon_phase()

    return {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "location": "Cape Cod, MA",
        "species": "Striped Bass",
        "tides": tides,
        "buoy": buoy,
        "weather": weather,
        "moon": moon,
    }


if __name__ == "__main__":
    import json
    data = get_all_conditions()
    print(json.dumps(data, indent=2, default=str))
