# DataOps AI Incident Investigator — Week 3 Agentic AI Project

A LangGraph workflow investigates **synthetic** ETL incidents, selects diagnostic tools, maintains state, retries transient failures, and interrupts before *simulated* recovery. Never connects to workplace infrastructure.

## Quick start (Windows / VS Code)

```powershell
cd C:\Personal\GenAcademy\Week3Agent\DATAOPS-AGENT
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env to put your OPENAI_API_KEY if you want actual LLM-driven tool selection.
python -m streamlit run app.py
```

**Important:** Without `OPENAI_API_KEY`, the project runs in **offline fallback mode**: tool selection follows transparent heuristic rules, not LLM reasoning. For an authentic agentic course demo, use your own valid API key. OpenAI API billing is separate from a ChatGPT subscription. **Never commit `.env`.**

For Windows CMD use `.venv\Scripts\activate.bat` instead of the PowerShell command.

## Demo sequence

1. Select `INC-003`: SQL timeout occurs once, and is retried automatically. Agent requests approval for a simulated verification rerun.
2. Choose **Reject** to show safety, or **Approve** to show synthetic resolution.
3. Select `INC-001`: missing source data causes human escalation, not an unsafe reload.
4. Select `INC-002`: dependency failure results in proposed recovery with approval interrupt.
5. Expand **Saved state** to see checkpoint values, and demonstrate reloading the thread ID.

## Agent control flow

`START -> decide -> use_tool -> decide (loop) -> diagnose -> [approval interrupt -> recover OR escalation] -> END`

Tools: `get_job_logs`, `run_validation_sql`, `get_job_dependencies`, `get_run_history`. LLM chooses the next tool when configured, with validation and a deterministic fallback when unavailable. Tool calls capped at 8; transient SQL reads retried once. Dangerous operations are **not available**: the final action only updates simulated state.

## Evals

```powershell
python -m pytest -q
```

Tests cover 4 synthetic incident root causes, timeout recovery, approval/rejection, tool allowlisting. Tests explicitly disable LLM calls to make repeatable assertions; these are not measurements of LLM decision quality. Add a separate LLM trajectory evaluation before claiming tool-choice accuracy.

## Files

- `app.py`: Streamlit interface and resume controls
- `src/agent.py`: LangGraph workflow and persistent checkpoint support
- `src/tools.py`: synthetic read-only tools
- `data/incidents.json`: test incidents and ground-truth labels
- `tests/test_agent.py`: deterministic evaluation suite
- `docs/project_documentation.md`: Google Docs-ready write-up
- `docs/demo_script.md`: 5-minute video outline

## GitHub

```powershell
git init
git add .
git commit -m "Build Week 3 DataOps agent MVP"
```

Create an empty repository on GitHub, then follow its on-screen commands to add `origin` and push your main branch. Never add your `.env`, `.venv`, or checkpoint DB.

## Limitations

Synthetic data; diagnosis is intentionally constrained to verified fixture signatures; LLM controls tool selection only. Local SQLite persistence is intended for a single-user demo. No production security model, real Databricks integration, or general SQL execution.
