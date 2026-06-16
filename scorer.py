"""
scorer.py
---------
Sends all environmental data + fishing reports to Claude and
returns a structured fishing forecast with:
  - Overall score (1–10)
  - Factor breakdown
  - Plain-language narrative
  - Hot/Cold report classifications
  - Top spot recommendations
"""

import json
import re
import anthropic


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_forecast_prompt(conditions: dict, reports: list[dict]) -> str:
    """
    Build the system + user prompt for Claude.
    Returns the user message string (system prompt is separate).
    """
    tides   = conditions.get("tides", {})
    buoy    = conditions.get("buoy", {})
    weather = conditions.get("weather", {})
    moon    = conditions.get("moon", {})

    # Format conditions block
    conditions_text = f"""
DATE/TIME: {conditions.get('fetched_at', 'Unknown')}
LOCATION: Cape Cod, MA
TARGET SPECIES: Striped Bass

--- TIDES (Chatham, MA) ---
Current stage: {tides.get('stage', 'unknown').upper()}
Last event: {tides.get('last_event_type', '?')} at {tides.get('last_event_time', '?')} ({tides.get('last_event_height', '?')} ft)
Next event: {tides.get('next_event_type', '?')} at {tides.get('next_event_time', '?')} ({tides.get('next_event_height', '?')} ft)
Hours until next event: {tides.get('hours_until_next', '?')}
Today's full tide schedule: {json.dumps(tides.get('all_events', []))}

--- WATER CONDITIONS (NOAA Buoy 44020, Nantucket Sound) ---
Water temperature: {buoy.get('water_temp_f', 'unavailable')}°F ({buoy.get('water_temp_c', '?')}°C)
Wave height: {buoy.get('wave_height_ft', 'unavailable')} ft
Buoy wind: {buoy.get('wind_speed_mph', 'unavailable')} mph from {buoy.get('wind_direction_label', '?')}
Observation time: {buoy.get('observation_time', 'unknown')}

--- WEATHER (Cape Cod) ---
Conditions: {weather.get('conditions', 'unknown')}
Wind: {weather.get('wind_speed_mph', 'unavailable')} mph from {weather.get('wind_direction_label', '?')} (gusts to {weather.get('wind_gusts_mph', '?')} mph)
Precipitation: {weather.get('precipitation_in', 0)} inches
Cloud cover: {weather.get('cloud_cover_pct', '?')}%

--- MOON ---
Phase: {moon.get('phase_name', 'unknown')}
Illumination: {moon.get('illumination_pct', '?')}%
Days into cycle: {moon.get('phase_days', '?')} of 29.5
Solunar score: {moon.get('solunar_score', '?')}/10
""".strip()

    # Format reports block
    if reports:
        reports_text = "\n\n--- RECENT FISHING REPORTS ---\n"
        for i, r in enumerate(reports, 1):
            reports_text += f"\nReport {i} [{r.get('source', 'unknown')}] — {r.get('date', 'recent')}:\n"
            reports_text += f"Title: {r.get('title', 'No title')}\n"
            if r.get("body"):
                reports_text += f"Body: {r['body']}\n"
    else:
        reports_text = "\n\n--- RECENT FISHING REPORTS ---\nNo recent reports available.\n"

    return conditions_text + reports_text


SYSTEM_PROMPT = """
You are ReelAI, an expert fishing forecast engine specialized in striped bass on Cape Cod, Massachusetts.

You have deep knowledge of:
- Striped bass behavior and biology (ideal water temps: 55–68°F, feeding triggers, migration patterns)
- Cape Cod geography: Chatham rips, Nauset Beach, Monomoy flats, Provincetown, Orleans, Eastham
- Tidal fishing: how tide stage and timing affect striper feeding (outgoing tides concentrate bait)
- Solunar theory and moon phase effects on fish activity
- Reading fishing reports: what "birds working", "bunker showing", "rips firing" actually mean
- Seasonal patterns: spring migration, summer holding, fall run (the "fall run" is peak season)
- Local lures and techniques: SP Minnow, Slug-Go, needlefish, eels, clams, live bait

Your job is to analyze the provided conditions and fishing reports, then return a structured JSON forecast.

SCORING CRITERIA for each factor (1–10):
- Water temp: 55–65°F = 9–10, 50–55°F or 65–68°F = 7–8, <48°F or >72°F = 2–4
- Tide timing: 2 hrs before/after high or low (the "change") = 9–10; slack water = 3–4
- Wind/surf: <10 mph = 9–10; 10–20 mph = 6–8; >20 mph = 3–5; onshore vs offshore matters
- Moon phase: within 2 days of new/full = 9–10; first/last quarter = 5–6; middle = 4–5
- Report sentiment: multiple slot fish, active bite = 9–10; nothing caught = 1–3; mixed = 5–7

ALWAYS return valid JSON in exactly this format — no markdown, no extra text:
{
  "score": <number 1-10, one decimal place>,
  "score_label": <"Dead" | "Slow" | "Fair" | "Good" | "Hot">,
  "narrative": "<2-3 sentence plain English summary of today's conditions and what they mean for fishing>",
  "factors": {
    "water_temp":   {"score": <1-10>, "label": "<brief label>", "note": "<one sentence>"},
    "tides":        {"score": <1-10>, "label": "<brief label>", "note": "<one sentence>"},
    "wind":         {"score": <1-10>, "label": "<brief label>", "note": "<one sentence>"},
    "moon":         {"score": <1-10>, "label": "<brief label>", "note": "<one sentence>"},
    "reports":      {"score": <1-10>, "label": "<brief label>", "note": "<one sentence>"}
  },
  "report_classifications": [
    {"source": "<source>", "title": "<title>", "classification": "<Hot|Warm|Neutral|Cold|Dead>", "reason": "<brief>"}
  ],
  "top_spots": [
    {"name": "<spot name>", "score": <1-10>, "timing": "<best window today>", "tip": "<one sentence>"}
  ],
  "technique_tip": "<1-2 sentences on best lure/technique given today's specific conditions>",
  "data_quality": "<Good|Partial|Limited — note any missing data>"
}
""".strip()


# ── Main scoring function ─────────────────────────────────────────────────────

def generate_forecast(conditions: dict, reports: list[dict], api_key: str) -> dict:
    """
    Send conditions + reports to Claude and return the parsed forecast dict.

    Args:
        conditions: Output from data_fetcher.get_all_conditions()
        reports:    Output from report_fetcher.get_all_reports()
        api_key:    Your Anthropic API key

    Returns:
        Parsed forecast dict, or error dict if something fails.
    """
    client = anthropic.Anthropic(api_key=api_key)

    user_message = build_forecast_prompt(conditions, reports)

    print("Sending to Claude for scoring...")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        raw_response = message.content[0].text.strip()

        # Strip any accidental markdown code fences
        raw_response = re.sub(r"^```(?:json)?\s*", "", raw_response)
        raw_response = re.sub(r"\s*```$", "", raw_response)

        forecast = json.loads(raw_response)

        # Attach the raw conditions for reference
        forecast["_conditions_snapshot"] = {
            "fetched_at": conditions.get("fetched_at"),
            "water_temp_f": conditions.get("buoy", {}).get("water_temp_f"),
            "tide_stage": conditions.get("tides", {}).get("stage"),
            "wind_mph": conditions.get("weather", {}).get("wind_speed_mph"),
            "moon_phase": conditions.get("moon", {}).get("phase_name"),
        }

        return forecast

    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse Claude response as JSON: {e}",
            "raw_response": raw_response if "raw_response" in locals() else "no response",
        }
    except anthropic.APIError as e:
        return {"error": f"Anthropic API error: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from data_fetcher import get_all_conditions
    from report_fetcher import get_all_reports

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set your ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        exit(1)

    print("=== ReelAI Forecast Generator ===\n")

    conditions = get_all_conditions()
    reports    = get_all_reports()

    print(f"\nFetched {len(reports)} fishing reports.")
    print("Generating forecast...\n")

    forecast = generate_forecast(conditions, reports, api_key)

    if "error" in forecast:
        print(f"Error: {forecast['error']}")
    else:
        print(f"SCORE: {forecast['score']}/10 — {forecast['score_label'].upper()}")
        print(f"\nNARRATIVE:\n{forecast['narrative']}")
        print("\nFACTORS:")
        for factor, data in forecast.get("factors", {}).items():
            print(f"  {factor:<12} {data['score']}/10  {data['label']} — {data['note']}")
        print("\nTOP SPOTS:")
        for spot in forecast.get("top_spots", []):
            print(f"  {spot['name']} ({spot['score']}/10) — {spot['timing']}")
        print(f"\nTECHNIQUE TIP:\n{forecast.get('technique_tip', '')}")
        print(f"\nDATA QUALITY: {forecast.get('data_quality', 'unknown')}")
