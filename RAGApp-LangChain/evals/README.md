# Center Copilot evaluation benchmark

This is a fixed development regression suite, not an unseen holdout or a production reliability claim. It has 30 cases: 10 SQL, 8 document, 8 combined, and 4 access/missing-evidence boundaries. The benchmark's reference date stays October 19, 2026.

## Run the suite

From the repository root:

```powershell
# No model calls: compare analytics with stored independent daily-row calculations.
.venv\Scripts\python.exe evals/run.py --mode offline --output data/evals/local_check

# Uses credits: 16 direct retrieval checks plus 30 agent questions.
.venv\Scripts\python.exe evals/run.py --mode all --output data/evals/my_run

# Resume the same run without repeating completed cases.
.venv\Scripts\python.exe evals/run.py --mode all --output data/evals/my_run --resume
```

Modes `retrieval` and `agent` run only the respective live stage. `--limit 6` limits the agent stage to the first six cases; it does not produce a balanced sample. Omit it for the full 30. Failed cases are also preserved and skipped on resume; use a new run directory to retry. The runner refuses to mix changed code, model, index, or benchmark inputs into an existing run.

`build_benchmark.py` regenerates the tracked `benchmark.json` using Python arithmetic over daily rows, not the analytics SQL view. Run it only when intentionally updating ground truth after dataset changes. Do not index any files in `evals/` or generated evaluation outputs as retrieval evidence.

## Understand the results

- `results.jsonl`: every case, question, check, elapsed time, returned chunk IDs, and agent answers/sources.
- `summary.json`: stage counts, retrieval recall, errors, configuration signature, and measurement limits.
- `human_review_template.csv`: blank review fields with each answer and its case-specific rubric. Copy it to `human_review.csv` before editing; resume regenerates only the template.

The offline stage checks actual calculations. The agent number screen only checks whether the expected magnitudes appear somewhere in the prose (within $0.51 for money or 0.11 for other numeric metrics). It allows positive shortfall magnitudes and rounding. It does not verify the right sign, unit, metric association, or surrounding explanation. A passed screen is not an accurate-answer verdict.

Retrieval recall@6 compares six retrieved chunks with explicitly labeled relevant chunk IDs. Micro recall pools relevant chunks across questions; macro recall averages per-question recall. Access checks inspect all source records returned to the agent, not just the final citations. These checks do not establish authenticated application authorization or complete policy-version correctness.

For each agent answer, a person should grade numerical correctness, citation support, causal caution, scope/abstention, and action quality as `pass`, `fail`, or `not_applicable`, with notes. Check each substantive claim against the exact retrieved passage and the SQL values. An uncertainty phrase does not excuse an unsupported claim elsewhere in the answer. No additional LLM judge is used automatically.

Suggested initial acceptance targets: all SQL calculations correct, retrieval recall@6 at least 90%, no source scope leaks, and all four boundary answers appropriate on qualitative review. The earlier 95% citation-support goal must be measured claim by claim; it cannot be inferred from valid citation IDs or this blank review sheet.

The runner follows the task-specific evaluation approach described in [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
