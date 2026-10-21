# Center Performance Copilot

A learning project that helps a daycare center director investigate weekly enrollment and revenue gaps using SQL calculations and cited operational documents.

## Build sequence

1. Define the business metrics and create the database schema.
2. Generate reproducible synthetic data and weekly operating reports.
3. Build and verify read-only SQL analytics tools.
4. Ingest, clean, chunk, and embed documents; index them in Pinecone.
5. Connect a LangChain agent to SQL and document search.
6. Add a Streamlit interface with source citations and refresh dates.
7. Evaluate calculations, retrieval, evidence support, and access boundaries.

## Agreed scope

- User: a center director, restricted to their assigned center and shared guidance.
- Reference date: the actual current date in America/Los_Angeles, resolved on every app run/rerun and agent request.
- Reporting week: Sunday through Saturday.
- Latest completed week: the Sunday–Saturday week immediately preceding the current reporting week; the current Saturday is not treated as complete until Sunday.
- History: a rolling 52 complete weeks ending on that latest completed Saturday.
- Data: 10 fictional centers with daily operating records, weekly targets, and weekly reports.
- Stack: Python, SQLite, LangChain, OpenAI models and embeddings, Pinecone, Streamlit.
- Embedding baseline: text-embedding-3-small; section-aware chunks around 500 tokens with 75-token overlap, to be tuned using evaluations.

## Metric contract for the prototype

- Revenue means synthetic earned tuition revenue for a service date, not cash collections.
- Enrollment means active enrolled full-time-equivalent (FTE) seats, allowing fractional schedules.
- Weekly enrollment is average enrolled FTE across open days, not a sum of daily enrollment.
- Staffed occupancy is enrolled FTE divided by staffed capacity, aggregated using open-day totals.
- Licensed capacity and staffed capacity are separate; neither guarantees availability in a particular age group.
- Weekly revenue variance is actual revenue minus target revenue; percentage variance is undefined when the target is zero.
- Closed days have zero earned revenue and zero staffed capacity; active enrollment can remain nonzero.
- Weekly targets are supplied independently and are never inferred from actual results.
- Compare completed weeks against target, previous week, and the four completed weeks preceding the selected week.
- Operational notes are evidence of reported conditions, not proof of financial causation.

These are explicit prototype definitions to validate with business owners before an internal deployment. The first version models center-level capacity; age-group and classroom constraints are a future extension.

## Repository layout

- `sql/schema.sql`: structured data contract.
- `src/center_copilot/`: data generation, analytics, retrieval, and agent code as they are built.
- `data/`: generated synthetic database and documents (excluded from Git).
- `evals/`: benchmark questions and expected evidence as they are built.

## Generate and inspect the synthetic dataset

Run from the repository root (Python standard library only):

```powershell
.venv\Scripts\python.exe src/center_copilot/generate_data.py
```

The generator refuses to overwrite an existing dataset. To generate a separate copy, use `--output data/comparison`.

Outputs:

- `data/center_performance.sqlite`: 10 centers, 3,640 daily rows, and 520 weekly targets.
- `data/documents/`: 520 weekly operating reports and four shared guidance documents, all explicitly fictional.
- `data/generation_summary.json`: latest-week figures and scenario labels for development and evaluation; do not ingest this file as retrieval evidence.
- `data/document_hashes.json`: hashes for checking document changes.

Start by reading `data/documents/C001_2026-10-11.md` and comparing it with C001 in `data/generation_summary.json`.

Three scenarios run during the final four completed weeks: C001 has a staffed capacity constraint, C002 has lower realized tuition, and C003 has a weaker enrollment pipeline. The other seven centers provide routine comparison data. These are deliberately simplified teaching scenarios, not forecasts or a full financial model.

Synthetic centers operate Monday through Friday except a fixed fictional closure calendar; reporting weeks still run Sunday through Saturday. Revenue is zero on closures under this prototype's simplifying billing assumption. Daily FTE is a generated operating snapshot; child starts and withdrawals do not reconcile it because child counts do not specify schedules or FTE.

Validation checks database integrity, foreign keys, row counts, complete seven-day weeks, date boundaries, capacity bounds, document existence, and independent latest-week arithmetic. A second generation was checked for byte-for-byte reproducibility.

## Current milestone

All seven prototype milestones and the first improvement iteration are implemented. The unchanged benchmark now retrieves all 24 labeled evidence chunks and passes 30/30 narrow automatic agent screens, with no validation errors. See `evals/FIX_RESULTS.md` for the before/after comparison and remaining qualitative issues. These development results do not establish production readiness.

## Run weekly analytics

```powershell
python src/center_copilot/analytics.py --assigned-center C001
python src/center_copilot/analytics.py --assigned-center C001 --week-start 2026-10-04
python -m unittest discover -s tests -v
```

The tool defaults to the latest completed week relative to the fixed reference date. Its JSON output includes actuals, targets, signed variances, previous-week comparisons, and averages of the four preceding completed weeks. The four-week baseline gives each weekly metric equal weight; it is not a pooled daily average. Raw revenue comparisons are not adjusted for differing open-day counts.

Missing comparison history is explicitly unavailable rather than silently replaced with a shorter average. Undefined percentage changes return null. Missing or incomplete selected weeks, non-Sunday starts, and current/future weeks are rejected.

The database connection is read-only, and SQL statements use bound parameters. `CenterAnalytics` binds the assigned center when it is constructed; the eventual agent-facing tool will accept only the reporting week. The CLI's `--assigned-center` is a developer simulation, not authentication: deployment must obtain the assigned center from trusted application identity.

`source.data_through` records the latest service date for this center, not an ingestion timestamp. Operational causes require document evidence; this tool only establishes numerical differences.

## Prepare and search document evidence

Use the project's virtual environment for retrieval and tests:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe src/center_copilot/retrieval.py prepare
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Preparation reads only the 524 Markdown files listed in the database manifest. It does not ingest generation summaries or evaluation labels. It cleans whitespace and HTML entities, preserves section headings and source references, and produces 2,084 chunks containing 94,235 embedding-input tokens for the current dataset. Each chunk is at most 500 tokens; long sections use 75-token overlap, while short sections remain intact. The first tokenizer run downloads a vocabulary file; preparation does not call the embedding API.

Inspect `data/retrieval/chunks.jsonl` and `data/retrieval/plan.json` before uploading. This MVP supports the generated Markdown corpus; PDF and DOCX extraction are not implemented.

Copy `.env.example` to `.env` if the file does not already exist, then enter `OPENAI_API_KEY` and `PINECONE_API_KEY` locally. Never paste keys into chat. Environment variables take precedence over `.env` values. The index name, cloud, and region are configurable; select a region available to your Pinecone account.

When keys are configured, these commands make real API requests and may use credits:

```powershell
.venv\Scripts\python.exe src/center_copilot/retrieval.py index --create-index
.venv\Scripts\python.exe src/center_copilot/retrieval.py search "What operating conditions should I investigate for my enrollment gap?" --assigned-center C001 --week-start 2026-10-11
```

The integration uses `text-embedding-3-small`, explicitly requests 1,536 dimensions, and uses a cosine dense-vector field named `embedding` in a Pinecone schema-based document index (Python SDK v10). It validates the index before spending embedding credits. An existing legacy vector index or an index with an incompatible field should be replaced with a separate compatible index name, not modified in place.

Embedding results are cached locally by model, dimensions, and exact input text. Repeated indexing reuses cached embeddings, although Pinecone upserts still occur. A changed corpus gets a separate deterministic namespace, so deleted documents from an earlier snapshot cannot enter new searches. The local active namespace switches only after all upload calls succeed. Search visibility is eventually consistent; allow a short delay after indexing. Old namespaces remain in Pinecone and require intentional cleanup if storage accumulates.

Search returns at most six passages, restricted to the assigned center's selected weekly report and shared guidance effective throughout the reporting week. The default retrieval now reserves three slots for report evidence (prioritizing director observations) and three for guidance. It uses retrieved operating observations to enrich the guidance query, preventing policy evidence from being crowded out by report sections. Unused slots are filled from remaining candidates; `top_k=1` retains a single dense search. Center assignment is bound outside the question, as with SQL; the CLI remains a developer identity simulation. Every result includes its source path, section, version, and document ID. Scores from separate report and guidance queries are not directly comparable or confidence probabilities.

`indexed_at_utc` records the successful upload time, not the reporting period. This step supplies manual refresh commands, not a nightly scheduler. Live API behavior and retrieval relevance must still be evaluated after credentials are configured.

API references used for the implementation: [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings) and [Pinecone SDK quickstart](https://sdk.pinecone.io/python/getting-started/quickstart.html).

## Ask the LangChain agent

```powershell
.venv\Scripts\python.exe src/center_copilot/agent.py "Why did my center miss its enrollment and revenue targets last week, and what three actions should I investigate?" --assigned-center C001
```

Add `--json` to inspect the answer, source metadata, and tool names. Use `--week-start YYYY-MM-DD` to select another completed Sunday-Saturday week. Each invocation is independent; follow-up conversational memory is not implemented.

The agent uses LangChain `create_agent` and an OpenAI chat model (default `gpt-4.1-mini`, configurable through `OPENAI_CHAT_MODEL` in `.env`). This is separate from the existing OpenAI embedding model; changing the chat model does not require re-embedding documents. Live questions use model API credits and may embed the retrieval question.

Two tools are available: `get_center_metrics` returns SQL actuals, targets, and comparisons; `search_center_documents` returns scoped report passages and guidance. Both are bound to the assigned center and selected week before the agent starts. The language model cannot pass a different center or reporting week through tool arguments.

Each tool registers its actual sources with a per-question citation ledger. The answer uses labels such as `[S1]`, and the CLI appends a source list built from that ledger. Grouped labels such as `[S1, S2]` are normalized to individual labels, and every ID is checked. Invalid or missing citations receive at most one model repair attempt with the existing evidence; a second invalid answer is rejected. A narrow guard also rejects explicit numeric EBITDA/profit-margin assertions because those metrics are unavailable. These checks do not prove that every statement is supported: claim-level grounding and numerical accuracy require evaluation and human review.

The prompt requires numerical questions to use SQL and causal investigations to use both tools, distinguishes observations from causation, and tells the model to acknowledge retrieval failures and missing evidence. These behavioral instructions are not a formal guarantee; the live C001 smoke test verified both tools were used for the demonstration question. Tool errors are surfaced as limitations rather than fabricated results.

Local tests cover the actual LangChain loop using a scripted model, immutable tool scope, document source registration, bounded citation repair, grouped and unknown IDs, unavailable financial metrics, retrieval coverage, analytics, and the interface. Run them with `.venv\Scripts\python.exe -m unittest discover -s tests -v` (33 tests after the first improvement iteration).

References: [LangChain agent quickstart](https://docs.langchain.com/oss/python/langchain/quickstart) and [OpenAI chat model documentation](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

## Use the local interface

The app resolves the current Los Angeles date each time it runs, including reruns in a long-lived server. It reuses a dataset only when its complete 52-week date window matches. At a Sunday rollover it generates a new local snapshot under `data/snapshots/<week-ending-date>/`, keeps older data and evaluation files, and selects the latest completed week. No model calls occur just to display metrics. For a new snapshot, the first submitted question also prepares and indexes its documents using API credits; the interface displays a notice before submission. Partial current weeks are excluded.

The original benchmark fixtures and historical results intentionally retain their original dates for repeatability. Their scores do not automatically apply to newly generated snapshots. `generation_summary.json` records a snapshot's generation date, while the interface and agent report the current run date.

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed in the terminal (normally `http://127.0.0.1:8501`). Keep the terminal running; press Ctrl+C to stop. The project configuration binds the server to loopback, and this milestone does not deploy or publish the application.

1. Select a fictional center and completed Sunday-Saturday week in the sidebar.
2. Review the revenue, enrollment, staffed occupancy, and capacity cards. Expand the eight-week revenue trend if helpful.
3. Submit a complete question. Each submission independently invokes the agent using your API credits; simply viewing metrics or changing selections makes no model calls.
4. Expand the answer's sources to inspect the exact retrieved passages or SQL calculation details. Download the answer and sources as JSON if needed.

Answers persist across ordinary Streamlit reruns without triggering another request. Changing the center or week clears the displayed answer. The interface does not provide conversational follow-up memory; include the full question each time.

Center selection is a demo control, not authenticated authorization. A production director view must bind the center to verified identity. The interface uses only the synthetic dataset and identifies it as fictional.

The dashboard reads SQLite directly; credentials are required only for agent requests. Connection and service failures show a concise error without provider error bodies or secret values. The document upload timestamp is displayed in America/Los_Angeles time, separately from the fixed dataset reference date.

For Windows/Python 3.13, the dependency file selects pandas 2.x and PyArrow 19.0.1 after Windows Application Control blocked a newer PyArrow binary during development. No Windows security settings are changed. Streamlit interaction tests use a mocked agent, so they do not make paid requests.

At the interface milestone, all 22 local tests and `pip check` passed. Streamlit AppTest verified initial metrics, center selection, scoped question submission, no duplicate requests on rerun, clearing answers when the reporting week changes, blank-question handling, and sanitized service errors. The local server returned HTTP 200 for its page and health endpoint during a startup check and was stopped afterward. A visual browser review and a live question through the browser remain manual checks; live agent execution was verified separately in the previous milestone.

## Evaluate the prototype

The tracked `evals/benchmark.json` contains 10 SQL, 8 document, 8 combined, and 4 boundary questions. See [evaluation instructions](evals/README.md) for local/live modes, resuming a run, and the manual review rubric. Evaluation files and answers are never ingested into Pinecone.

The first full run checked all 30 agent questions, 16 direct retrieval questions, and 10 independent numeric cases. Numerical checks passed; retrieval micro recall@6 was 83.3% (20/24 labeled chunks), below the 90% target. Twenty-eight agent answers passed the narrow automatic screens and two raised validation errors. All 26 local regression tests passed. These counts do not establish semantic answer accuracy or citation support; see [baseline findings](evals/BASELINE_RESULTS.md).

After the approved fixes, the same benchmark found 24/24 relevant chunks (100% recall@6), all 30 agent screens passed, and no errors occurred. The previously failing count and EBITDA questions now complete; EBITDA is correctly identified as unavailable. See [improvement results](evals/FIX_RESULTS.md) for details and known remaining issues. To rerun without overwriting either comparison, use a new output folder, for example `.venv\Scripts\python.exe evals/run.py --mode all --output data/evals/next_run`.

No API keys are required until the document embedding step. Keep credentials in a local `.env` file and never commit them.
