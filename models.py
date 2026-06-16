"""
models.py
---------
SQLAlchemy ORM models for ReelAI.

Tables:
  - locations           : fishing locations (Cape Cod spots)
  - conditions          : hourly environmental snapshots
  - tide_events         : discrete high/low tide events
  - fishing_reports     : scraped + user-submitted reports
  - report_classifications : AI classifications of reports
  - forecasts           : generated forecast scores + narratives

Run `alembic upgrade head` to create these tables after setup.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Locations ─────────────────────────────────────────────────────────────────

class Location(Base):
    """
    A named fishing location. Allows the system to track multiple spots
    and eventually serve per-spot forecasts.
    """
    __tablename__ = "locations"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:           Mapped[str]           = mapped_column(String(100), unique=True, nullable=False)
    region:         Mapped[str]           = mapped_column(String(100), default="Cape Cod, MA")
    latitude:       Mapped[float]         = mapped_column(Float, nullable=False)
    longitude:      Mapped[float]         = mapped_column(Float, nullable=False)
    tide_station_id:Mapped[Optional[str]] = mapped_column(String(20))   # NOAA station ID
    buoy_station_id:Mapped[Optional[str]] = mapped_column(String(20))   # NDBC buoy ID
    notes:          Mapped[Optional[str]] = mapped_column(Text)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    conditions:  Mapped[list["Conditions"]]    = relationship(back_populates="location")
    tide_events: Mapped[list["TideEvent"]]     = relationship(back_populates="location")
    forecasts:   Mapped[list["Forecast"]]      = relationship(back_populates="location")

    def __repr__(self):
        return f"<Location {self.name}>"


# ── Conditions ────────────────────────────────────────────────────────────────

class Conditions(Base):
    """
    One row per environmental data fetch (hourly).
    Stores both parsed columns (for querying) and raw JSON (for re-processing).
    """
    __tablename__ = "conditions"

    id:              Mapped[int]           = mapped_column(Integer, primary_key=True)
    location_id:     Mapped[int]           = mapped_column(ForeignKey("locations.id"), nullable=False)
    fetched_at:      Mapped[datetime]      = mapped_column(DateTime, nullable=False, index=True)

    # Water
    water_temp_f:    Mapped[Optional[float]] = mapped_column(Float)
    water_temp_c:    Mapped[Optional[float]] = mapped_column(Float)
    wave_height_ft:  Mapped[Optional[float]] = mapped_column(Float)
    water_clarity:   Mapped[Optional[str]]   = mapped_column(String(50))  # clear/murky/off-color

    # Wind (from buoy + weather API, keep both)
    wind_speed_mph:  Mapped[Optional[float]] = mapped_column(Float)
    wind_gusts_mph:  Mapped[Optional[float]] = mapped_column(Float)
    wind_direction:  Mapped[Optional[str]]   = mapped_column(String(10))  # NE, SW, etc.
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float)

    # Tide (summary — full events stored in tide_events table)
    tide_stage:      Mapped[Optional[str]]   = mapped_column(String(20))  # rising/falling
    hours_to_next_tide: Mapped[Optional[float]] = mapped_column(Float)
    next_tide_type:  Mapped[Optional[str]]   = mapped_column(String(5))   # H or L

    # Weather
    weather_conditions: Mapped[Optional[str]] = mapped_column(String(100))
    precipitation_in:   Mapped[Optional[float]] = mapped_column(Float)
    cloud_cover_pct:    Mapped[Optional[int]]   = mapped_column(Integer)

    # Moon
    moon_phase:      Mapped[Optional[str]]   = mapped_column(String(50))
    moon_illumination_pct: Mapped[Optional[int]] = mapped_column(Integer)
    solunar_score:   Mapped[Optional[float]] = mapped_column(Float)

    # Raw API responses — never throw these away
    raw_buoy_data:   Mapped[Optional[dict]]  = mapped_column(JSON)
    raw_weather_data:Mapped[Optional[dict]]  = mapped_column(JSON)
    raw_tide_data:   Mapped[Optional[dict]]  = mapped_column(JSON)
    raw_moon_data:   Mapped[Optional[dict]]  = mapped_column(JSON)

    # Relationships
    location:   Mapped["Location"]        = relationship(back_populates="conditions")
    forecasts:  Mapped[list["Forecast"]]  = relationship(back_populates="conditions")

    __table_args__ = (
        Index("ix_conditions_location_fetched", "location_id", "fetched_at"),
    )

    def __repr__(self):
        return f"<Conditions {self.fetched_at} water={self.water_temp_f}°F tide={self.tide_stage}>"


# ── Tide Events ───────────────────────────────────────────────────────────────

class TideEvent(Base):
    """
    One row per predicted high or low tide event.
    NOAA returns these as discrete predictions — store them as such.
    """
    __tablename__ = "tide_events"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    location_id:  Mapped[int]      = mapped_column(ForeignKey("locations.id"), nullable=False)
    event_time:   Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    event_type:   Mapped[str]      = mapped_column(String(1), nullable=False)  # "H" or "L"
    height_ft:    Mapped[float]    = mapped_column(Float, nullable=False)
    station_id:   Mapped[str]      = mapped_column(String(20))
    fetched_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    location: Mapped["Location"] = relationship(back_populates="tide_events")

    __table_args__ = (
        # Prevent duplicate tide events for the same station + time
        UniqueConstraint("station_id", "event_time", "event_type", name="uq_tide_event"),
    )

    def __repr__(self):
        return f"<TideEvent {self.event_type} {self.event_time} {self.height_ft}ft>"


# ── Fishing Reports ───────────────────────────────────────────────────────────

class FishingReport(Base):
    """
    One row per scraped or user-submitted fishing report.
    Stores both the parsed content and the raw original.
    """
    __tablename__ = "fishing_reports"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    source:       Mapped[str]           = mapped_column(String(100), nullable=False)  # "On The Water", "Stripersonline", "user"
    title:        Mapped[str]           = mapped_column(String(300), nullable=False)
    body_text:    Mapped[Optional[str]] = mapped_column(Text)
    report_date:  Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    url:          Mapped[Optional[str]] = mapped_column(String(500))
    author:       Mapped[Optional[str]] = mapped_column(String(100))  # username or "anonymous"

    # Location context extracted from the report
    location_tags:  Mapped[Optional[list]] = mapped_column(JSON)  # ["Chatham", "Monomoy", ...]
    species_tags:   Mapped[Optional[list]] = mapped_column(JSON)  # ["striped bass", "bluefish"]
    technique_tags: Mapped[Optional[list]] = mapped_column(JSON)  # ["SP Minnow", "live eel"]

    # User-submitted fields (NULL for scraped reports)
    fish_count:     Mapped[Optional[int]]   = mapped_column(Integer)
    fish_size_in:   Mapped[Optional[float]] = mapped_column(Float)  # average size in inches
    is_user_submitted: Mapped[bool]         = mapped_column(Boolean, default=False)

    # Deduplication
    content_hash:  Mapped[Optional[str]]  = mapped_column(String(64), unique=True)  # MD5 of title+body
    raw_html:      Mapped[Optional[str]]  = mapped_column(Text)  # original HTML, for re-parsing

    scraped_at:    Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    classifications: Mapped[list["ReportClassification"]] = relationship(
        back_populates="report", order_by="ReportClassification.classified_at.desc()"
    )

    __table_args__ = (
        Index("ix_reports_source_date", "source", "report_date"),
    )

    @property
    def latest_classification(self) -> Optional["ReportClassification"]:
        return self.classifications[0] if self.classifications else None

    def __repr__(self):
        return f"<FishingReport [{self.source}] {self.title[:50]}>"


# ── Report Classifications ────────────────────────────────────────────────────

class ReportClassification(Base):
    """
    AI classification of a fishing report.
    Kept separate from FishingReport so we can re-classify as the model improves.
    One report can have many classifications over time — always use the latest.
    """
    __tablename__ = "report_classifications"

    id:             Mapped[int]      = mapped_column(Integer, primary_key=True)
    report_id:      Mapped[int]      = mapped_column(ForeignKey("fishing_reports.id"), nullable=False)
    classification: Mapped[str]      = mapped_column(String(20), nullable=False)  # Hot/Warm/Neutral/Cold/Dead
    confidence:     Mapped[Optional[float]] = mapped_column(Float)  # 0.0–1.0
    reason:         Mapped[Optional[str]]   = mapped_column(Text)
    model_version:  Mapped[str]      = mapped_column(String(50), default="claude-sonnet-4-5")
    classified_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    report: Mapped["FishingReport"] = relationship(back_populates="classifications")

    __table_args__ = (
        Index("ix_classifications_report_date", "report_id", "classified_at"),
    )

    def __repr__(self):
        return f"<Classification {self.classification} ({self.confidence:.0%})>"


# ── Forecasts ─────────────────────────────────────────────────────────────────

class Forecast(Base):
    """
    One row per generated AI forecast.
    This is your most valuable table — it becomes your back-test dataset.
    """
    __tablename__ = "forecasts"

    id:              Mapped[int]      = mapped_column(Integer, primary_key=True)
    location_id:     Mapped[int]      = mapped_column(ForeignKey("locations.id"), nullable=False)
    conditions_id:   Mapped[Optional[int]] = mapped_column(ForeignKey("conditions.id"))
    generated_at:    Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    forecast_for:    Mapped[datetime] = mapped_column(DateTime, nullable=False)  # the date this forecast covers

    # The score
    score:           Mapped[float]    = mapped_column(Float, nullable=False)
    score_label:     Mapped[str]      = mapped_column(String(20))  # Hot/Good/Fair/Slow/Dead

    # Factor sub-scores (1-10 each)
    factor_water_temp: Mapped[Optional[float]] = mapped_column(Float)
    factor_tides:      Mapped[Optional[float]] = mapped_column(Float)
    factor_wind:       Mapped[Optional[float]] = mapped_column(Float)
    factor_moon:       Mapped[Optional[float]] = mapped_column(Float)
    factor_reports:    Mapped[Optional[float]] = mapped_column(Float)

    # AI narrative
    narrative:       Mapped[Optional[str]]   = mapped_column(Text)
    technique_tip:   Mapped[Optional[str]]   = mapped_column(Text)

    # Full AI response stored as JSON (includes top spots, report classifications, etc.)
    full_response:   Mapped[Optional[dict]]  = mapped_column(JSON)

    # Model tracking
    model_version:   Mapped[str]      = mapped_column(String(50), default="claude-sonnet-4-5")
    data_quality:    Mapped[Optional[str]]   = mapped_column(String(50))  # Good/Partial/Limited

    # Reports used in this forecast (stored as list of IDs)
    report_ids_used: Mapped[Optional[list]]  = mapped_column(JSON)

    # Relationships
    location:   Mapped["Location"]    = relationship(back_populates="forecasts")
    conditions: Mapped[Optional["Conditions"]] = relationship(back_populates="forecasts")

    __table_args__ = (
        Index("ix_forecasts_location_date", "location_id", "forecast_for"),
    )

    def __repr__(self):
        return f"<Forecast {self.forecast_for.date()} score={self.score} [{self.score_label}]>"
