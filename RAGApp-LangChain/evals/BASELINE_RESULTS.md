# First evaluation baseline

Run date: October 20, 2026 (America/Los_Angeles). Dataset reference: October 19, 2026. Chat model: `gpt-4.1-mini`. Embeddings: `text-embedding-3-small`.

## Measured results

| Measure | Result | Interpretation |
| --- | --- | --- |
| Independent SQL checks | 10/10 cases passed | Weekly calculations matched Python arithmetic over daily rows and targets. |
| Retrieval micro recall@6 | 20/24 relevant chunks, 83.3% | Below the initial 90% target. |
| Retrieval macro recall@6 | 87.5% across 16 questions | Average recall per question; differs from pooled chunk recall. |
| Source scope checks | No violations detected in returned evidence | Applies to these cases, not authenticated production authorization. |
| Agent automatic screens | 28/30 passed; 2 ValueErrors | Routing/scope/expected-number screens, not 93.3% answer correctness. |
| Local regression tests | 26 passed | Includes analytics, retrieval, agent, interface, and evaluator tests. |

The output is saved in `data/evals/first_full_run/summary.json` and `results.jsonl`. The configuration signature in the summary identifies the evaluated code, dataset, benchmark, index state, and model. This is one run of a development suite, not an independent holdout result.

## What the benchmark found

The four missed relevant chunks were capacity guidance for C001 and discount policy for C002, each in two combined questions. All eight document-only questions found their labeled evidence. Broad investigation queries retrieved the center report but sometimes omitted the relevant playbook/policy. The agent can rewrite a query, so direct retrieval recall and the final agent's evidence need separate interpretation.

`sql_08` (C003 inquiry/tour/enrollment/withdrawal counts) and `boundary_03` (unavailable EBITDA/profit margin) raised `ValueError`. The first-run logger retained exception type only, so the exact validation reason is not established. Investigate the rejection path before changing it; do not bypass source validation merely to increase completion rate.

Codex qualitatively inspected all 28 returned answers and the two error records. This is an assistant review, not an independent human review or a claim-level citation-support score. The nine returned numerical-only answers matched the requested benchmark facts, and the eight document-only answers reflected the relevant source content. Combined answers exposed additional issues that the automatic screens do not detect:

- `mix_01` and `mix_07` gave five next steps despite the prompt's three-step limit.
- `mix_02` claimed enrollment starts/withdrawals were not large enough to explain the gap, without a supporting financial decomposition.
- `mix_04`, `mix_06`, and `mix_08` introduced attendance into an enrolled-FTE analysis. The dataset does not contain attendance; stable enrollment does not establish stable attendance.
- Several answers used grouped citation syntax such as `[S1, S3]`. The current validator recognizes individual `[S1]` labels only, so grouped-only references can be omitted from the exported source list and unknown IDs within groups are not checked.
- `boundary_01` correctly refused another center. `boundary_02` acknowledged that the vacancy's exact financial contribution is unknown, but its opening description of the full target variance as revenue "lost" should be clearer. `boundary_04` refused another week but suggested selecting a week that is not available as a completed period. `boundary_03` returned no answer because of the validation error.

## Recommended next iteration

1. Capture safe, specific validation reasons and handle grouped citations correctly, keeping nonexistent-source checks.
2. Improve retrieval coverage for relevant policy/playbook evidence in combined investigations; measure recall again against this unchanged benchmark.
3. Tighten claim grounding: no attendance conclusions, unsupported financial attribution, or uncited action claims. Keep recommendations to three items.
4. Rerun in a new output directory and compare with this preserved baseline. Obtain a human's claim-level review using `human_review_template.csv` before reporting the 95% citation-support goal as achieved.

No prompt or retrieval behavior was tuned after this run. Only evaluation visibility was added to the agent result (`available_sources`) before the benchmark, so the baseline remains available for a later comparison.
