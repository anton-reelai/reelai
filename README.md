# 🎣 ReelAI — AI-Powered Fishing Forecast

AI-powered striped bass fishing forecast for Cape Cod, MA.
Combines NOAA environmental data, fishing reports, and Claude AI to produce a simple 1–10 fishing score.

---

## Repo structure

```
reelai/
├── app.py              # Streamlit web app (run this)
├── data_fetcher.py     # NOAA tides, buoy, weather, moon phase
├── report_fetcher.py   # Fishing report scraper (RSS + forums)
├── scorer.py           # Claude AI scoring engine
├── models.py           # SQLAlchemy database models
├── database.py         # DB connection, init, and seed
├── db_writer.py        # Save conditions/reports/forecasts to DB
├── scheduler.py        # Automated hourly/daily data pipeline
├── requirements.txt
├── .env.example        # Copy to .env and fill in your values
└── .streamlit/
    └── secrets.toml    # Streamlit Cloud secrets (don't commit)
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourusername/reelai.git
cd reelai
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env and add your keys
```

Required variables:
- `ANTHROPIC_API_KEY` — get at [console.anthropic.com](https://console.anthropic.com)
- `DATABASE_URL` — your Postgres connection string (see Database Setup below)

### 3. Set up the database

```bash
python database.py
```

This creates all tables and seeds the Cape Cod fishing locations.

### 4. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) and click **Generate Forecast**.

### 5. (Optional) Run the scheduler

In a separate terminal, start the background scheduler that auto-fetches data:

```bash
python scheduler.py
```

---

## Database Setup (Supabase — free)

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. Go to **Settings → Database → Connection string → URI**
4. Copy the URI and add it to your `.env` as `DATABASE_URL`
5. Run `python database.py` to create tables

---

## Deploy to Streamlit Cloud (free)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo, set main file to `app.py`
4. Under **Advanced settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   DATABASE_URL = "postgresql://..."
   ```
5. Click Deploy — you'll get a live URL in ~2 minutes

---

## Data sources

| Source | Data | Cost |
|--------|------|------|
| NOAA Tides & Currents | Tide predictions | Free |
| NOAA NDBC Buoy 44020 | Water temp, waves | Free |
| Open-Meteo | Wind, weather | Free |
| Moon phase | Calculated locally | Free |
| On The Water (RSS) | Fishing reports | Free |
| Salty Cape (RSS) | Fishing reports | Free |
| Stripersonline | Forum reports | Free (scrape) |
| Claude API | AI scoring | ~$0.02/forecast |

---

## Running individual modules

```bash
# Test data fetching (no API key needed)
python data_fetcher.py
python report_fetcher.py

# Run a full forecast from the CLI
python scorer.py

# Set up / verify database
python database.py

# Start the automated scheduler
python scheduler.py
```
