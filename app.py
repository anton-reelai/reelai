"""
app.py
------
Streamlit web app for ReelAI.
Run with: streamlit run app.py

Requires:
  pip install streamlit anthropic requests feedparser beautifulsoup4

Set your API key:
  export ANTHROPIC_API_KEY=sk-ant-...
  OR create a .env file with ANTHROPIC_API_KEY=sk-ant-...
"""

import os
import json
import streamlit as st
from datetime import datetime

# Load .env file if present (optional — install python-dotenv to use)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from data_fetcher import get_all_conditions
from report_fetcher import get_all_reports
from scorer import generate_forecast


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ReelAI — Cape Cod Fishing Forecast",
    page_icon="🎣",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  .score-circle {
    background: #0E7C7B;
    border-radius: 50%;
    width: 140px; height: 140px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    margin: 0 auto 12px auto;
    border: 4px solid #1AA7A6;
  }
  .score-num  { font-size: 3rem; font-weight: 700; color: white; line-height: 1; }
  .score-sub  { font-size: 0.8rem; color: #D6EAF8; }
  .score-label{ font-size: 1rem; font-weight: 600; color: #F4A623; letter-spacing: 2px; }
  .factor-bar { background: #e0e0e0; border-radius: 4px; height: 8px; margin: 4px 0 8px 0; }
  .factor-fill{ height: 8px; border-radius: 4px; }
  .report-card{
    border: 1px solid #ddd; border-radius: 8px;
    padding: 12px; margin-bottom: 10px;
    background: #fafafa;
  }
  .hot   { color: #0E7C7B; font-weight: 600; }
  .warm  { color: #2e7d32; }
  .cold  { color: #c62828; }
  .neutral{ color: #757575; }
  .pill {
    display: inline-block; padding: 2px 10px;
    border-radius: 12px; font-size: 0.75rem;
    font-weight: 600; margin-left: 8px;
  }
  .pill-hot    { background: #e0f2f1; color: #00695c; }
  .pill-warm   { background: #e8f5e9; color: #2e7d32; }
  .pill-neutral{ background: #f5f5f5; color: #616161; }
  .pill-cold   { background: #fff3e0; color: #e65100; }
  .pill-dead   { background: #fce4ec; color: #b71c1c; }
</style>
""", unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────────

def score_color(score: float) -> str:
    if score >= 8:  return "#0E7C7B"
    if score >= 6:  return "#2e7d32"
    if score >= 4:  return "#f9a825"
    return "#c62828"

def score_emoji(label: str) -> str:
    return {"Hot": "🔥", "Good": "✅", "Fair": "🟡", "Slow": "🔵", "Dead": "💀"}.get(label, "🎣")

def render_factor_bar(score: float):
    pct   = int(score * 10)
    color = score_color(score)
    st.markdown(
        f'<div class="factor-bar"><div class="factor-fill" style="width:{pct}%;background:{color};"></div></div>',
        unsafe_allow_html=True
    )

def classification_pill(cls: str) -> str:
    cls_lower = cls.lower()
    return f'<span class="pill pill-{cls_lower}">{cls}</span>'


# ── Sidebar — API key ─────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Settings")
    api_key_input = st.text_input(
        "Anthropic API Key",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Get your key at console.anthropic.com"
    )
    st.markdown("---")
    st.markdown("**Data sources**")
    use_reports = st.checkbox("Include fishing reports", value=True)
    st.markdown("---")
    st.caption("ReelAI prototype · Cape Cod, MA · Striped Bass")


# ── Main app ──────────────────────────────────────────────────────────────────

st.title("🎣 ReelAI")
st.markdown("**AI-powered striped bass forecast · Cape Cod, MA**")
st.markdown("---")

# Check for API key
api_key = api_key_input or os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    st.warning("⚠️ Enter your Anthropic API key in the sidebar to generate a forecast.")
    st.stop()

# Generate button
col_btn, col_info = st.columns([2, 5])
with col_btn:
    generate = st.button("🔄 Generate Forecast", type="primary", use_container_width=True)
with col_info:
    st.caption(f"Last updated: {st.session_state.get('last_updated', 'Never')}")

# Cache forecast in session state so it doesn't re-run on every interaction
if generate or "forecast" not in st.session_state:
    if not generate and "forecast" not in st.session_state:
        st.info("Click 'Generate Forecast' to fetch current conditions and produce a score.")
        st.stop()

    with st.spinner("Fetching conditions and reports..."):
        conditions = get_all_conditions()
        reports    = get_all_reports(include_manual=True) if use_reports else []

    with st.spinner("Asking Claude to score the fishing..."):
        forecast = generate_forecast(conditions, reports, api_key)

    if "error" in forecast:
        st.error(f"Error generating forecast: {forecast['error']}")
        st.stop()

    st.session_state["forecast"]    = forecast
    st.session_state["conditions"]  = conditions
    st.session_state["reports"]     = reports
    st.session_state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

forecast   = st.session_state["forecast"]
conditions = st.session_state["conditions"]
reports    = st.session_state["reports"]

# ── Score section ─────────────────────────────────────────────────────────────

score = forecast.get("score", 0)
label = forecast.get("score_label", "")
emoji = score_emoji(label)
color = score_color(score)

st.markdown("### Today's Forecast")
col_score, col_narrative = st.columns([1, 3])

with col_score:
    st.markdown(
        f"""
        <div class="score-circle" style="border-color:{color}; background:{color};">
          <div class="score-num">{score}</div>
          <div class="score-sub">out of 10</div>
        </div>
        <div style="text-align:center;">
          <span class="score-label">{emoji} {label.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_narrative:
    st.markdown(f"#### {forecast.get('narrative', '')}")
    snap = forecast.get("_conditions_snapshot", {})
    if snap:
        st.caption(
            f"🌡️ Water: {snap.get('water_temp_f','?')}°F  |  "
            f"🌊 Tide: {snap.get('tide_stage','?').title()}  |  "
            f"💨 Wind: {snap.get('wind_mph','?')} mph  |  "
            f"🌙 Moon: {snap.get('moon_phase','?')}"
        )
    tip = forecast.get("technique_tip")
    if tip:
        st.info(f"🎯 **Technique tip:** {tip}")

st.markdown("---")

# ── Factor breakdown ──────────────────────────────────────────────────────────

st.markdown("### Condition Factors")
factors = forecast.get("factors", {})
factor_cols = st.columns(len(factors))

factor_labels = {
    "water_temp": "💧 Water Temp",
    "tides":      "🌊 Tides",
    "wind":       "💨 Wind",
    "moon":       "🌙 Moon",
    "reports":    "📋 Reports",
}

for col, (key, data) in zip(factor_cols, factors.items()):
    with col:
        fscore = data.get("score", 0)
        fcolor = score_color(fscore)
        st.metric(
            label=factor_labels.get(key, key.title()),
            value=f"{fscore}/10",
            delta=data.get("label", ""),
        )
        render_factor_bar(fscore)
        st.caption(data.get("note", ""))

st.markdown("---")

# ── Top spots ─────────────────────────────────────────────────────────────────

spots = forecast.get("top_spots", [])
if spots:
    st.markdown("### 📍 Top Spots Today")
    spot_cols = st.columns(min(len(spots), 3))
    for col, spot in zip(spot_cols, spots[:3]):
        with col:
            scolor = score_color(spot.get("score", 0))
            st.markdown(
                f"""
                <div style="border:1px solid {scolor};border-radius:8px;padding:12px;margin-bottom:8px;">
                  <div style="font-weight:600;font-size:1rem;">{spot['name']}</div>
                  <div style="font-size:1.5rem;font-weight:700;color:{scolor};">{spot.get('score',0)}/10</div>
                  <div style="font-size:0.8rem;color:#555;margin:4px 0;">⏰ {spot.get('timing','')}</div>
                  <div style="font-size:0.85rem;">{spot.get('tip','')}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    st.markdown("---")

# ── Report classifications ────────────────────────────────────────────────────

classifications = forecast.get("report_classifications", [])
if classifications:
    st.markdown("### 📰 Recent Report Analysis")
    for rc in classifications:
        cls = rc.get("classification", "Neutral")
        pill = classification_pill(cls)
        st.markdown(
            f"""
            <div class="report-card">
              <div><strong>{rc.get('source','')}</strong>{pill}</div>
              <div style="font-size:0.9rem;margin:4px 0;">{rc.get('title','')}</div>
              <div style="font-size:0.82rem;color:#555;">{rc.get('reason','')}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown("---")

# ── Raw data expander ─────────────────────────────────────────────────────────

with st.expander("🔬 Raw conditions data"):
    tab1, tab2, tab3, tab4 = st.tabs(["Tides", "Buoy", "Weather", "Moon"])
    with tab1:
        st.json(conditions.get("tides", {}))
    with tab2:
        st.json(conditions.get("buoy", {}))
    with tab3:
        st.json(conditions.get("weather", {}))
    with tab4:
        st.json(conditions.get("moon", {}))

with st.expander("🤖 Full AI response"):
    display = {k: v for k, v in forecast.items() if not k.startswith("_")}
    st.json(display)

with st.expander("📋 Fetched fishing reports"):
    for r in reports:
        st.markdown(f"**[{r.get('source')}]** {r.get('title','')}")
        if r.get("body"):
            st.caption(r["body"][:300] + "..." if len(r.get("body","")) > 300 else r.get("body",""))
        st.markdown("---")
