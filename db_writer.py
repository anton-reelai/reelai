"""
db_writer.py
------------
Functions that save fetched data and forecasts into the database.
Called by the scheduler and by app.py after each forecast is generated.

Each function is safe to call repeatedly — it checks for duplicates
before inserting so you don't end up with redundant rows.
"""

import hashlib
from datetime import datetime
from typing import Optional

from models import Conditions, TideEvent, FishingReport, ReportClassification, Forecast, Location
from database import get_session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _content_hash(text: str) -> str:
    """MD5 hash of a string — used to detect duplicate reports."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def get_or_create_location(name: str = "Chatham Rips") -> int:
    """Return the location ID for the given name. Raises if not found."""
    with get_session() as session:
        loc = session.query(Location).filter_by(name=name).first()
        if not loc:
            raise ValueError(
                f"Location '{name}' not found in database. "
                "Run `python database.py` to seed locations first."
            )
        return loc.id


# ── Save conditions ───────────────────────────────────────────────────────────

def save_conditions(conditions: dict, location_name: str = "Chatham Rips") -> int:
    """
    Save an environmental conditions snapshot to the database.

    Args:
        conditions: Output from data_fetcher.get_all_conditions()
        location_name: Name of the location (must exist in locations table)

    Returns:
        The ID of the newly created Conditions row.
    """
    location_id = get_or_create_location(location_name)

    tides   = conditions.get("tides", {})
    buoy    = conditions.get("buoy", {})
    weather = conditions.get("weather", {})
    moon    = conditions.get("moon", {})

    # Parse fetched_at string to datetime
    fetched_at_str = conditions.get("fetched_at", "")
    try:
        fetched_at = datetime.strptime(fetched_at_str, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        fetched_at = datetime.utcnow()

    row = Conditions(
        location_id     = location_id,
        fetched_at      = fetched_at,

        # Water
        water_temp_f    = buoy.get("water_temp_f"),
        water_temp_c    = buoy.get("water_temp_c"),
        wave_height_ft  = buoy.get("wave_height_ft"),

        # Wind
        wind_speed_mph  = weather.get("wind_speed_mph"),
        wind_gusts_mph  = weather.get("wind_gusts_mph"),
        wind_direction  = weather.get("wind_direction_label"),
        wind_direction_deg = weather.get("wind_direction_deg"),

        # Tide summary
        tide_stage          = tides.get("stage"),
        hours_to_next_tide  = tides.get("hours_until_next"),
        next_tide_type      = tides.get("next_event_type"),

        # Weather
        weather_conditions  = weather.get("conditions"),
        precipitation_in    = weather.get("precipitation_in"),
        cloud_cover_pct     = weather.get("cloud_cover_pct"),

        # Moon
        moon_phase              = moon.get("phase_name"),
        moon_illumination_pct   = moon.get("illumination_pct"),
        solunar_score           = moon.get("solunar_score"),

        # Raw API responses — keep everything
        raw_buoy_data    = buoy,
        raw_weather_data = weather,
        raw_tide_data    = tides,
        raw_moon_data    = moon,
    )

    with get_session() as session:
        session.add(row)
        session.flush()  # Get the ID before commit
        new_id = row.id

    print(f"  ✅ Saved conditions (id={new_id}, temp={row.water_temp_f}°F, tide={row.tide_stage})")
    return new_id


# ── Save tide events ──────────────────────────────────────────────────────────

def save_tide_events(conditions: dict, location_name: str = "Chatham Rips") -> int:
    """
    Save today's tide high/low events to the database.
    Skips events that already exist (unique constraint on station+time+type).

    Returns:
        Number of new events inserted.
    """
    location_id  = get_or_create_location(location_name)
    tides        = conditions.get("tides", {})
    station_id   = "8447930"  # Chatham NOAA station
    all_events   = tides.get("all_events", [])
    inserted     = 0

    with get_session() as session:
        for event in all_events:
            try:
                event_time = datetime.strptime(event["time"], "%I:%M %p").replace(
                    year=datetime.now().year,
                    month=datetime.now().month,
                    day=datetime.now().day,
                )
            except (ValueError, KeyError):
                continue

            # Check for duplicate
            exists = session.query(TideEvent).filter_by(
                station_id=station_id,
                event_time=event_time,
                event_type=event.get("type"),
            ).first()

            if not exists:
                session.add(TideEvent(
                    location_id = location_id,
                    station_id  = station_id,
                    event_time  = event_time,
                    event_type  = event.get("type", "?"),
                    height_ft   = float(event.get("height", 0)),
                ))
                inserted += 1

    print(f"  ✅ Saved {inserted} new tide events (skipped {len(all_events) - inserted} duplicates)")
    return inserted


# ── Save fishing reports ──────────────────────────────────────────────────────

def save_reports(reports: list[dict]) -> list[int]:
    """
    Save a list of fishing reports to the database.
    Skips reports that are duplicates (matched by content hash).

    Args:
        reports: Output from report_fetcher.get_all_reports()

    Returns:
        List of IDs for newly inserted reports.
    """
    new_ids = []

    with get_session() as session:
        for r in reports:
            # Build a content hash from title + body to detect duplicates
            hash_input = (r.get("title", "") + r.get("body", "")).strip()
            if not hash_input:
                continue
            chash = _content_hash(hash_input)

            # Skip if we already have this report
            exists = session.query(FishingReport).filter_by(content_hash=chash).first()
            if exists:
                continue

            # Parse date
            report_date = None
            date_str = r.get("date", "")
            if date_str and date_str != "unknown" and date_str != "recent":
                try:
                    report_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

            row = FishingReport(
                source            = r.get("source", "unknown"),
                title             = r.get("title", "")[:300],
                body_text         = r.get("body", ""),
                report_date       = report_date,
                url               = r.get("url", "")[:500] if r.get("url") else None,
                is_user_submitted = r.get("source") == "User report",
                content_hash      = chash,
            )
            session.add(row)
            session.flush()
            new_ids.append(row.id)

    print(f"  ✅ Saved {len(new_ids)} new reports (skipped {len(reports) - len(new_ids)} duplicates)")
    return new_ids


# ── Save report classifications ───────────────────────────────────────────────

def save_classifications(forecast: dict, report_ids: list[int]) -> None:
    """
    Save AI report classifications from a forecast response to the database.

    Args:
        forecast:   Output from scorer.generate_forecast()
        report_ids: List of FishingReport IDs that were classified
    """
    classifications = forecast.get("report_classifications", [])
    if not classifications or not report_ids:
        return

    with get_session() as session:
        for cls_data, report_id in zip(classifications, report_ids):
            row = ReportClassification(
                report_id      = report_id,
                classification = cls_data.get("classification", "Neutral"),
                reason         = cls_data.get("reason", ""),
                model_version  = "claude-sonnet-4-5",
            )
            session.add(row)

    print(f"  ✅ Saved {len(classifications)} report classifications")


# ── Save forecast ─────────────────────────────────────────────────────────────

def save_forecast(
    forecast: dict,
    conditions_id: Optional[int] = None,
    report_ids: Optional[list[int]] = None,
    location_name: str = "Chatham Rips",
) -> int:
    """
    Save a generated forecast to the database.

    Args:
        forecast:      Output from scorer.generate_forecast()
        conditions_id: ID of the Conditions row this forecast was built from
        report_ids:    IDs of FishingReport rows used in this forecast
        location_name: Name of the location

    Returns:
        The ID of the newly created Forecast row.
    """
    if "error" in forecast:
        raise ValueError(f"Cannot save an error forecast: {forecast['error']}")

    location_id = get_or_create_location(location_name)
    factors     = forecast.get("factors", {})

    row = Forecast(
        location_id    = location_id,
        conditions_id  = conditions_id,
        forecast_for   = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        generated_at   = datetime.utcnow(),

        score          = forecast.get("score", 0),
        score_label    = forecast.get("score_label", ""),

        factor_water_temp = factors.get("water_temp", {}).get("score"),
        factor_tides      = factors.get("tides", {}).get("score"),
        factor_wind       = factors.get("wind", {}).get("score"),
        factor_moon       = factors.get("moon", {}).get("score"),
        factor_reports    = factors.get("reports", {}).get("score"),

        narrative      = forecast.get("narrative", ""),
        technique_tip  = forecast.get("technique_tip", ""),

        full_response  = {k: v for k, v in forecast.items() if not k.startswith("_")},
        model_version  = "claude-sonnet-4-5",
        data_quality   = forecast.get("data_quality", ""),
        report_ids_used = report_ids or [],
    )

    with get_session() as session:
        session.add(row)
        session.flush()
        new_id = row.id

    print(f"  ✅ Saved forecast (id={new_id}, score={row.score}, label={row.score_label})")
    return new_id


# ── Full pipeline save ────────────────────────────────────────────────────────

def save_full_pipeline(
    conditions: dict,
    reports: list[dict],
    forecast: dict,
    location_name: str = "Chatham Rips",
) -> dict:
    """
    Save an entire pipeline run (conditions + tide events + reports + forecast)
    in one call. Returns a dict of all the new IDs created.

    This is what the scheduler calls after each run.
    """
    print("\n💾 Saving to database...")

    results = {}

    try:
        results["conditions_id"] = save_conditions(conditions, location_name)
    except Exception as e:
        print(f"  ⚠️  Failed to save conditions: {e}")
        results["conditions_id"] = None

    try:
        results["tide_events_count"] = save_tide_events(conditions, location_name)
    except Exception as e:
        print(f"  ⚠️  Failed to save tide events: {e}")

    try:
        results["report_ids"] = save_reports(reports)
    except Exception as e:
        print(f"  ⚠️  Failed to save reports: {e}")
        results["report_ids"] = []

    try:
        save_classifications(forecast, results.get("report_ids", []))
    except Exception as e:
        print(f"  ⚠️  Failed to save classifications: {e}")

    try:
        results["forecast_id"] = save_forecast(
            forecast,
            conditions_id = results.get("conditions_id"),
            report_ids    = results.get("report_ids", []),
            location_name = location_name,
        )
    except Exception as e:
        print(f"  ⚠️  Failed to save forecast: {e}")
        results["forecast_id"] = None

    print(f"💾 Done. forecast_id={results.get('forecast_id')}\n")
    return results
