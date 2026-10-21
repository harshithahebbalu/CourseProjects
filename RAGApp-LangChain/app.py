r"""Run with: .venv\Scripts\python.exe -m streamlit run app.py"""

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import altair as alt
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.analytics import CenterAnalytics
from center_copilot.reporting import runtime_date
from center_copilot.runtime_data import active_data_dir
from center_copilot.dashboard import center_options, completed_weeks, revenue_trend

st.set_page_config(page_title="Center Performance Copilot", page_icon="🌱", layout="wide")
st.title("Center Performance Copilot")
st.caption("Understand your weekly performance. Investigate the gap. Check the evidence.")

REFERENCE_DATE = runtime_date()
with st.spinner("Preparing the current reporting window…"):
    DATA = active_data_dir(REFERENCE_DATE)
DATABASE = DATA / "center_performance.sqlite"
if st.session_state.get("dataset_path") != str(DATA):
    st.session_state["dataset_path"] = str(DATA)
    st.session_state.pop("week", None)

try:
    centers = center_options(DATABASE)
except sqlite3.Error:
    st.error("The synthetic dataset is unavailable. Generate the dataset before starting the app.")
    st.stop()
if not centers:
    st.error("No centers are available in the dataset.")
    st.stop()

with st.sidebar:
    st.subheader("Your weekly review")
    st.caption("Synthetic-data demo • center selection simulates director access.")
    names = {c["center_id"]: c["center_name"] for c in centers}
    center = st.selectbox("Center", list(names), format_func=lambda c: f"{c} · {names[c]}", key="center")
    weeks = completed_weeks(DATABASE, center, REFERENCE_DATE)
    if not weeks:
        st.info("This center has no complete reporting weeks.")
        st.stop()
    week = st.selectbox("Reporting week", weeks, key="week", format_func=lambda w:
                        f"{date.fromisoformat(w):%b %d, %Y} – {date.fromisoformat(w) + timedelta(days=6):%b %d, %Y}")
    st.caption("Sunday–Saturday • completed weeks only")
    st.divider()
    st.caption(f"App date: {REFERENCE_DATE:%B %d, %Y} · Los Angeles")
    st.caption("Fictional centers, figures, and operating guidance. No real child or family records.")

scope = (str(DATA), center, week, str(REFERENCE_DATE))
if st.session_state.get("answer_scope") != scope:
    st.session_state["answer_scope"] = scope
    st.session_state.pop("copilot_result", None)
    st.session_state.pop("asked_question", None)
    st.session_state.pop("copilot_error", None)

try:
    metrics = CenterAnalytics(DATABASE, center).weekly_performance(week)
except (ValueError, sqlite3.Error):
    st.error("Weekly metrics could not be loaded for this selection.")
    st.stop()

actuals = metrics["actuals"]
targets = metrics["targets"] or {}
st.subheader(f"{names[center]} · weekly snapshot")
st.caption(f"Week ending {date.fromisoformat(metrics['week_end']):%B %d, %Y} · "
           f"Records available through {metrics['source']['data_through']}")

def number(value, pattern):
    return "—" if value is None else format(value, pattern)


revenue, enrollment, occupancy, capacity = st.columns(4)
with revenue:
    delta = metrics["versus_target"]["revenue"]["difference"]
    st.metric("Earned tuition revenue", "$" + number(actuals["actual_revenue"], ",.0f"),
              None if delta is None else f"${delta:+,.0f} vs target")
    st.caption("Target: $" + number(targets.get("target_revenue"), ",.0f"))
with enrollment:
    delta = metrics["versus_target"]["enrollment_fte"]["difference"]
    st.metric("Average enrolled FTE", number(actuals["avg_enrolled_fte"], ".1f"),
              None if delta is None else f"{delta:+.1f} FTE vs target")
    st.caption("Target: " + number(targets.get("target_avg_enrolled_fte"), ".1f") + " FTE")
with occupancy:
    st.metric("Staffed occupancy", number(actuals["staffed_occupancy"], ".1%"))
    st.caption("Enrollment ÷ staffed capacity across open days")
with capacity:
    st.metric("Average staffed capacity", number(actuals["avg_staffed_capacity"], ".1f"))
    st.caption(f"Licensed capacity: {metrics['center']['licensed_capacity']}")

with st.expander("Revenue trend · up to eight completed weeks"):
    trend = pd.DataFrame(revenue_trend(DATABASE, center, week))
    trend["week_start"] = pd.to_datetime(trend["week_start"])
    trend["Week beginning"] = trend["week_start"].dt.strftime("%b %d")
    trend["Reporting week"] = trend["week_start"].map(
        lambda start: f"{start:%b %d, %Y} – {start.date() + timedelta(days=6):%b %d, %Y}")
    trend = trend.rename(columns={"actual_revenue": "Actual revenue", "target_revenue": "Target revenue"})
    chart_data = trend.melt(id_vars=["Week beginning", "Reporting week"],
                            value_vars=["Actual revenue", "Target revenue"], var_name="Series", value_name="Revenue")
    chart = alt.Chart(chart_data).mark_line(point=True).encode(
        x=alt.X("Week beginning:O", sort=trend["Week beginning"].tolist(), title="Reporting week beginning Sunday",
                axis=alt.Axis(labelAngle=0, labelOverlap=False)),
        y=alt.Y("Revenue:Q", title="Weekly tuition revenue ($)", axis=alt.Axis(format="$,.0f")),
        color=alt.Color("Series:N", title=None, scale=alt.Scale(
            domain=["Actual revenue", "Target revenue"], range=["#146B61", "#B87B36"])),
        tooltip=[alt.Tooltip("Reporting week:N"), alt.Tooltip("Series:N"), alt.Tooltip("Revenue:Q", format="$,.2f")],
    )
    st.altair_chart(chart, width="stretch", alt="Actual and target weekly tuition revenue, labeled by Sunday week start.")
    st.caption("Each point totals one Sunday–Saturday reporting week. Hover over a point for the full date range and revenue. Different numbers of open days can affect comparisons.")

st.divider()
st.subheader("Ask about this week")
st.caption(f"Current selection: {center} · {metrics['week_start']} to {metrics['week_end']}. Change the center or reporting week in the sidebar, then ask again.")
st.caption("Each question is answered independently for the selected center and week. Requests use your API credits.")
if (DATA / "runtime_snapshot.json").exists() and not (DATA / "retrieval/index_state.json").exists():
    st.info("A new completed week is ready. Your first question will also prepare its document search using API credits; later questions reuse it.")
with st.form("ask_copilot"):
    question = st.text_area("Your question", value="Why did my center miss its revenue target last week, and what should I investigate?",
                            height=95, max_chars=2000, key="question")
    submitted = st.form_submit_button("Ask copilot", type="primary")

if submitted:
    st.session_state.pop("copilot_result", None)
    st.session_state.pop("copilot_error", None)
    st.session_state["asked_question"] = question.strip()
    if not question.strip():
        st.session_state["copilot_error"] = "Enter a question before asking the copilot."
    else:
        with st.spinner("Checking center metrics and relevant guidance…"):
            try:
                from center_copilot.agent import answer_question
                st.session_state["copilot_result"] = answer_question(question, center, week, DATA)
            except Exception as exc:
                if getattr(exc, "code", None):
                    st.session_state["copilot_error"] = "The answer could not be verified against its evidence. Please rephrase your question or try again."
                else:
                    st.session_state["copilot_error"] = (f"The copilot could not complete this request ({type(exc).__name__}). "
                        "Check API connectivity, credentials, model access, and the document index, then try again.")

if st.session_state.get("copilot_error"):
    st.error(st.session_state["copilot_error"])

result = st.session_state.get("copilot_result")
if result:
    with st.chat_message("user"):
        st.write(st.session_state["asked_question"])
    with st.chat_message("assistant"):
        st.markdown(result["answer"])
        st.caption("Check the cited evidence before acting. Reported conditions do not prove the cause of a revenue gap.")
    st.subheader("Evidence behind the answer")
    for source in result["sources"]:
        if source["kind"] == "sql":
            with st.expander(f"{source['citation']} Weekly metrics · {center} · {week}"):
                st.caption("Calculated from daily records and approved synthetic weekly targets.")
                st.json({k: metrics[k] for k in ("actuals", "targets", "versus_target", "previous_week", "prior_four_weeks")})
        else:
            with st.expander(f"{source['citation']} {source['title']} · {source['section']}"):
                st.caption(f"{source['source_path']} · version {source['version']}")
                st.text(source.get("text", "Passage text unavailable in this earlier answer; ask again to retrieve it."))
    st.download_button("Download answer and sources", json.dumps(result, indent=2),
                       file_name=f"{center}_{week}_review.json", mime="application/json")

with st.sidebar:
    state_path = DATA / "retrieval/index_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            uploaded = datetime.fromisoformat(state["indexed_at_utc"]).astimezone(ZoneInfo("America/Los_Angeles"))
            st.caption(f"Documents uploaded: {uploaded:%b %d, %Y %I:%M %p %Z}")
        except (ValueError, KeyError):
            st.caption("Document upload time unavailable.")
    else:
        st.caption("Document index is not ready; metrics remain available.")
