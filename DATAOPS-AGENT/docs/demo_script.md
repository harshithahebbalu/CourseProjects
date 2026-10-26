# Demo script (target 3–4 minutes; maximum 5 minutes)

**0:00–0:35 — Context.** “I'm a data engineer; investigating failed pipelines means inspecting logs, SQL validations, and upstream dependencies. I built a DataOps incident investigator to orchestrate these tasks.”

**0:35–1:10 — Architecture.** Show `src/agent.py`. “LangGraph controls the loop, tool calls, persistent SQLite state, bounded retries and an interrupt for human approval. Streamlit is the UI. Synthetic JSON is our test fixture.” Say whether the current demo is LLM-driven or offline fallback; don't misrepresent the mode.

**1:10–2:20 — Live demo.** Launch app. Select INC-003, start investigation; show timeout then retry in tool history, root cause, approval checkpoint. Reject first (no recovery), then start a second run and approve to show simulated completion.

**2:20–3:10 — Second case.** Run INC-001, show human escalation for missing source data. Expand checkpoint state and show tool results and status.

**3:10–3:45 — Evals.** In VS Code terminal run `python -m pytest -q` and show actual output. Mention these are deterministic control-flow tests, not LLM quality scores.

**3:45–4:15 — Vibe coding and lessons.** “I used ChatGPT to brainstorm, scope, design workflow and memory, and generate code in iterations. Key lesson: state and approval boundaries matter more than a single prompt. Future improvement: authorized Databricks tools and evaluation of LLM tool choices.”

Recording tip: Windows Snipping Tool screen recording or PowerPoint screen recording; upload resulting video wherever course instructions require. If available, use speaker notes rather than reading the whole script.
