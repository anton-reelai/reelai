"""
database.py
-----------
Database connection, session management, and setup.
Uses SQLAlchemy with a PostgreSQL connection string from the environment.

Usage:
    from database import get_session, init_db

    # Create all tables (run once)
    init_db()

    # Use a session
    with get_session() as session:
        session.add(some_model_instance)
        session.commit()
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from models import Base


# ── Connection ────────────────────────────────────────────────────────────────

def get_database_url() -> str:
    """
    Read the database URL from the environment.
    Set DATABASE_URL in your .env file or hosting platform secrets.

    Supabase example:
      DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

    Local Postgres example:
      DATABASE_URL=postgresql://postgres:password@localhost:5432/reelai
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError(
            "DATABASE_URL environment variable is not set.\n"
            "Add it to your .env file:\n"
            "  DATABASE_URL=postgresql://user:password@host:5432/reelai"
        )
    # Supabase (and some other hosts) return postgres:// — SQLAlchemy needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


# Build the engine once at import time
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_pre_ping=True,       # Test connections before using them
            pool_size=5,              # Keep 5 connections open
            max_overflow=10,          # Allow up to 10 extra connections under load
            echo=False,               # Set to True to log all SQL (useful for debugging)
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


# ── Session context manager ───────────────────────────────────────────────────

@contextmanager
def get_session() -> Session:
    """
    Provide a transactional scope around a series of operations.

    Usage:
        with get_session() as session:
            session.add(record)
            session.commit()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Init / setup ──────────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables defined in models.py.
    Safe to run multiple times — won't overwrite existing tables.
    Call this once when you first set up the database.
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("✅ Database tables created (or already exist).")


def check_connection():
    """Verify the database is reachable. Returns True if connected."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection successful.")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def seed_locations():
    """
    Insert the default Cape Cod fishing locations.
    Safe to run multiple times — skips existing locations.
    """
    from models import Location

    locations = [
        Location(
            name="Chatham Rips",
            region="Cape Cod, MA",
            latitude=41.6688,
            longitude=-69.9634,
            tide_station_id="8447930",
            buoy_station_id="44020",
            notes="Premier striper spot. Best on outgoing tide. Access by boat or charter.",
        ),
        Location(
            name="Nauset Beach",
            region="Cape Cod, MA",
            latitude=41.8279,
            longitude=-69.9510,
            tide_station_id="8447930",
            buoy_station_id="44020",
            notes="Long barrier beach. Walk-on access. Best at first light on outgoing tide.",
        ),
        Location(
            name="Monomoy Flats",
            region="Cape Cod, MA",
            latitude=41.5579,
            longitude=-69.9954,
            tide_station_id="8447930",
            buoy_station_id="44020",
            notes="Shallow tidal flats. Wade at low tide. Outstanding fall run fishing.",
        ),
        Location(
            name="Provincetown",
            region="Cape Cod, MA",
            latitude=42.0509,
            longitude=-70.1854,
            tide_station_id="8443970",
            buoy_station_id="44020",
            notes="Tip of the Cape. Race Point beach. Strong tidal currents concentrate bait.",
        ),
        Location(
            name="Orleans / Rock Harbor",
            region="Cape Cod, MA",
            latitude=41.7926,
            longitude=-70.0034,
            tide_station_id="8447930",
            buoy_station_id="44020",
            notes="Town creek and outer beach. Good access for surfcasters.",
        ),
    ]

    with get_session() as session:
        for loc in locations:
            existing = session.query(Location).filter_by(name=loc.name).first()
            if not existing:
                session.add(loc)
                print(f"  Added location: {loc.name}")
            else:
                print(f"  Skipped (already exists): {loc.name}")

    print("✅ Locations seeded.")


if __name__ == "__main__":
    print("=== ReelAI Database Setup ===\n")
    check_connection()
    init_db()
    seed_locations()
