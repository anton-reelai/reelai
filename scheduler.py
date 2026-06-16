"""
scheduler.py
------------
Background scheduler that automatically:
  - Fetches conditions from NOAA + weather every hour
  - Scrapes fishing reports every 6 hours
  - Generates and saves a fresh AI forecast every morning at 5 AM

Run standalone:
    python scheduler.py

Or import and start from app.py for an all-in-one deployment.

Requires DATABASE_URL and ANTHROPIC_API_KEY in environment.
"""

import os
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from data_fetcher import get_all_conditions
from report_fetcher import get_all_reports
from scorer import generate_forecast
from db_writer import save_full_pipeline, save_conditions, save_tide_events, save_reports


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("reelai.scheduler")


# ── Job functions ─────────────────────────────────────────────────────────────

def job_fetch_conditions():
    """
    Hourly job: fetch NOAA + weather conditions and save to DB.
    Does NOT generate a forecast — that's the morning job.
    """
    log.info("▶ [hourly] Fetching conditions...")
    try:
        conditions = get_all_conditions()
        save_conditions(conditions)
        save_tide_events(conditions)
        log.info("✅ [hourly] Conditions saved.")
    except Exception as e:
        log.error(f"❌ [hourly] Failed to fetch/save conditions: {e}")


def job_fetch_reports():
    """
    Every 6 hours: scrape fishing reports and save new ones to DB.
    """
    log.info("▶ [6h] Fetching fishing reports...")
    try:
        reports = get_all_reports(include_manual=False)
        save_reports(reports)
        log.info(f"✅ [6h] Reports job complete.")
    except Exception as e:
        log.error(f"❌ [6h] Failed to fetch/save reports: {e}")


def job_generate_forecast():
    """
    Daily 5 AM job: fetch fresh conditions + reports, generate AI forecast,
    and save everything to the database.
    """
    log.info("▶ [daily] Generating morning forecast...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("❌ [daily] ANTHROPIC_API_KEY not set — skipping forecast.")
        return

    try:
        conditions = get_all_conditions()
        reports    = get_all_reports(include_manual=False)
        forecast   = generate_forecast(conditions, reports, api_key)

        if "error" in forecast:
            log.error(f"❌ [daily] Forecast error: {forecast['error']}")
            return

        result = save_full_pipeline(conditions, reports, forecast)
        log.info(f"✅ [daily] Forecast saved. score={forecast.get('score')} id={result.get('forecast_id')}")

    except Exception as e:
        log.error(f"❌ [daily] Forecast job failed: {e}", exc_info=True)


# ── Scheduler setup ───────────────────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    """
    Build and return a configured BackgroundScheduler.
    Call .start() on the returned object to begin running jobs.
    """
    scheduler = BackgroundScheduler(timezone="America/New_York")

    # Fetch conditions every hour at :05 past (give APIs time to update)
    scheduler.add_job(
        job_fetch_conditions,
        trigger=CronTrigger(minute=5),
        id="fetch_conditions",
        name="Hourly conditions fetch",
        replace_existing=True,
        misfire_grace_time=300,  # Allow up to 5 min late start
    )

    # Fetch reports every 6 hours
    scheduler.add_job(
        job_fetch_reports,
        trigger=CronTrigger(hour="0,6,12,18", minute=15),
        id="fetch_reports",
        name="6-hour report scrape",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Generate full forecast at 5 AM daily
    scheduler.add_job(
        job_generate_forecast,
        trigger=CronTrigger(hour=5, minute=0),
        id="generate_forecast",
        name="Daily 5 AM forecast",
        replace_existing=True,
        misfire_grace_time=1800,  # Allow up to 30 min late
    )

    return scheduler


# ── Standalone run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    log.info("=== ReelAI Scheduler Starting ===")
    log.info("Jobs:")
    log.info("  - Conditions:  every hour at :05")
    log.info("  - Reports:     every 6 hours at :15")
    log.info("  - Forecast:    daily at 5:00 AM ET")
    log.info("")

    # Run each job once immediately on startup so you don't have to wait
    log.info("Running all jobs once on startup...")
    job_fetch_conditions()
    job_fetch_reports()
    job_generate_forecast()

    scheduler = create_scheduler()
    scheduler.start()

    log.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Shutting down scheduler...")
        scheduler.shutdown()
        log.info("Done.")
