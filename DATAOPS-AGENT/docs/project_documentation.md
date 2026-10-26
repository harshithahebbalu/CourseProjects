# Week 3 — DataOps AI Incident Investigator

## Project overview

Data pipeline failures are frequently investigated manually by inspecting logs, validating data, and checking upstream dependencies. This project prototypes an agentic investigator that selects diagnostic tools, accumulates evidence, maintains workflow state, tolerates temporary tool errors, and pauses for human authorization before any simulated recovery.

**User:** Data engineer responding to an ETL incident. **Interaction:** Streamlit local web UI. **Architecture:** LangGraph state graph, optional OpenAI LLM for tool selection, SQLite checkpointing, synthetic tool adapters, and pytest.

## Dataset used

`data/incidents.json` contains four entirely synthetic incidents (no proprietary information): (1) missing plan allocations, (2) upstream pipeline failure, (3) transient SQL timeout, and (4) inconclusive evidence. Each includes descriptive logs, validation checks, dependency status, historical run descriptions, ground-truth root cause, and a simulated recovery recommendation.

## How the agent works

The agent chooses its next tool from `get_job_logs`, `run_validation_sql`, `get_job_dependencies`, `get_run_history`, or `finish`. After each tool result, it updates the investigation state and decides again. It has a maximum of eight diagnostic calls and retries transient timeouts once. The diagnosis logic uses evidence checks and escalates rather than claiming certainty when evidence is insufficient. If a simulated recovery is recommended, LangGraph `interrupt()` requires an explicit approve/reject response. `SqliteSaver` stores checkpoints by thread ID.

**Important mode distinction:** With an OpenAI API key, an LLM chooses diagnostic actions. Without it, a rules-based fallback maintains a runnable offline demo; it should not be presented as equivalent LLM agent behavior.

## Prompts used during AI-assisted vibe coding

The project was developed through iterative prompts to ChatGPT. Representative prompts from the actual planning process:

1. “I need to build week 3 project in my course ... an agent that decides what to do next, calls tools, holds state across steps, recovers from errors, and hands off to a human.”
2. “What do you suggest we should build that would add value to my work as well?”
3. “Explain me each step and ask me for approval before building anything.”
4. “How is the state stored? Are we using any memory framework? Can we add evals to this? Do I need to login to LangGraph? ... Can we do this on notebook?”
5. “I approve generating the full runnable MVP project ZIP now, including LangGraph, SQLite persistence, simulated tools, human approval, Streamlit, and minimal evals.”

The agent's own decision prompt is in `src/agent.py` and restricts tool selection to an allowlist, requires adaptive use of evidence, and forbids unnecessary repeat calls.

## Iterations

- **Initial proposal:** full DataOps pipeline incident investigator with Databricks integration.
- **Scope decision:** hybrid architecture, using simulated incidents first with swappable tool interfaces.
- **Workflow refinement:** dynamic tool selection, bounded retries, persistent state, human approval.
- **Architecture refinement:** SQLite LangGraph checkpoints, Streamlit UI, local pytest evals; defer long-term memory and LangSmith.
- **Deadline-focused MVP:** build a single-user runnable package with four synthetic incidents and minimal safety/evaluation tests.

## Testing and observations

**Fill in after running locally:** Paste the output of `python -m pytest -q`, the tested application mode (LLM / offline fallback), and what you observed in the UI. Do not claim the tests passed until you have run them.

Potential lessons to discuss: persisted state differs from cross-incident memory; an explicit graph interrupt provides a stronger approval boundary than a prompt instruction; error recovery must be bounded; offline heuristic fallback is useful for UI testing but does not prove agent reasoning quality; deterministic tests validate control flow while LLM behavior needs separate evals.

## Limitations and next steps

The dataset is fictional and recovery is simulated. Root-cause matching is evidence-guarded but domain-specific, not a general diagnostic inference model. Future work: authorized read-only Databricks job and SQL APIs, cross-incident memory, richer LLM trajectory evals, observability, and secure role-based approval.

## Deliverables

- GitHub repository URL: **[add after upload]**
- Demo video URL (<=5 min): **[add after recording]**
- Run instructions and code: `README.md`
