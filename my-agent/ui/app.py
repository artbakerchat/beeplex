"""Beeplex Copilot - local web UI.

A thin browser console over the my-agent tools. Runs entirely on your
machine; no AgentCore deployment needed.

Run from the my-agent folder:
    streamlit run ui/app.py
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "ui"))

from my_agent.main import (  # noqa: E402
    BEEPLEX_DIR,
    _beeplex,
    bee_diary,
    fetch_conversations,
    generate_report,
    score_conversations,
)
from components.conversation_cards import conversation_cards  # noqa: E402


def _clean(v):
    """Make a beeplex cell JSON-safe for the browser component."""
    import math

    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v)

st.set_page_config(page_title="Beeplex Copilot", page_icon="🐝", layout="wide")

st.html("""
<style>
  .bee-hero {
    background: linear-gradient(135deg, #E8A317 0%, #C77F0A 100%);
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 4px 14px rgba(200, 130, 10, 0.25);
  }
  .bee-hero .icon { font-size: 52px; line-height: 1; }
  .bee-hero h1 {
    color: #FFFDF5; margin: 0; font-size: 30px; font-weight: 700;
  }
  .bee-hero p { color: #FFF3D6; margin: 4px 0 0 0; font-size: 15px; }
</style>
<div class="bee-hero">
  <div class="icon">🐝</div>
  <div>
    <h1>Beeplex Copilot</h1>
    <p>Local console for your Bee conversations &mdash; no deployment needed.</p>
  </div>
</div>
""")

with st.sidebar:
    st.header("Setup")
    found = BEEPLEX_DIR.is_dir()
    st.write("beeplex folder:", "found" if found else "MISSING")
    st.code(str(BEEPLEX_DIR))
    if not found:
        st.error("Set BEEPLEX_DIR to point at your beeplex checkout.")
    limit = st.slider("Conversations", 1, 10, 5)
    st.divider()
    st.caption("Model: ca.amazon.nova-micro-v1:0 (ca-central-1)")

tab_fetch, tab_score, tab_report, tab_diary, tab_pick = st.tabs(
    ["Conversations", "Scores", "Report", "Diary", "Picker"]
)

with tab_fetch:
    st.subheader("Recent conversations")
    if st.button("Fetch", key="fetch"):
        with st.spinner("Fetching from beeplex..."):
            st.text(fetch_conversations(limit=limit))

with tab_score:
    st.subheader("Engagement & forward motion")
    if st.button("Score", key="score"):
        with st.spinner("Scoring..."):
            st.text(score_conversations(limit=limit))

with tab_report:
    st.subheader("Reports")
    st.warning("Writes .docx / .xlsx / .pptx into beeplex/family/ and refreshes the dashboard.")
    if st.button("Generate report", key="report"):
        with st.spinner("Generating... (this can take a minute)"):
            st.text(generate_report(limit=10))

with tab_diary:
    st.subheader("Bee's diary")
    st.caption("Persona mode: who Bee has become, in its own first-person voice.")
    if st.button("Read today's entry", key="diary"):
        with st.spinner("Bee is writing..."):
            st.markdown(bee_diary(limit=limit))

with tab_pick:
    st.subheader("Pick a conversation")
    st.caption(
        "Tier-2 custom component: click a card in the browser — "
        "the choice travels back to Python."
    )
    if st.button("Load conversations", key="pick_load"):
        with st.spinner("Fetching from beeplex..."):
            bee_fetcher = _beeplex()
            rows, _info = bee_fetcher.fetch_report_data(limit=limit)
            st.session_state["pick_cards"] = [
                {
                    "date": _clean(row.get("Recording_Date")),
                    "title": _clean(row.get("Session_Title")),
                    "topic": _clean(row.get("Key_Topic")),
                }
                for row in rows
            ]
    cards = st.session_state.get("pick_cards", [])
    if cards:
        picked = conversation_cards(cards, key="picker")
        if picked:
            st.success(f"Picked in the browser: {picked.get('title')}")
            st.json(picked)
