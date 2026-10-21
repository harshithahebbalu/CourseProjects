# First improvement iteration

The same 30 development questions and 24 labeled relevant passages were reused. The baseline is preserved in `data/evals/first_full_run`; the new run is in `data/evals/after_fixes`. No re-embedding of the document corpus or changes to expected answers were needed.

| Measure | Baseline | After fixes |
| --- | --- | --- |
| Independent SQL cases | 10/10 | 10/10 |
| Retrieval micro recall@6 | 20/24 (83.3%) | 24/24 (100%) |
| Retrieval macro recall@6 | 87.5% | 100% |
| Agent automatic screens | 28/30 | 30/30 |
| Agent errors | 2 | 0 |
| Source scope violations detected | 0 | 0 |

These are development-suite results. In particular, 30/30 screens passing does not mean every claim in every answer is correct. Human review is still pending, and the 95% claim-level citation-support target has not been measured.

## Diagnosis and changes

Reproducing the original failures established that both omitted source citations. The numerical count answer was otherwise correct. The EBITDA candidate also incorrectly substituted $28,900 of earned tuition revenue for EBITDA; it was blocked by validation rather than delivered to the user. The captured diagnosis is in `data/evals/failure_diagnosis.json`.

- Grouped references such as `[S1, S2]` now normalize to `[S1][S2]`. Every label is validated, including unknown IDs within a group. Sources cited only in a group now appear in the exported source list.
- Missing or invalid citations get at most one model repair attempt using the same available evidence. A second invalid result is still rejected; the application never blindly appends a source to a claim. Tests cover both successful repair and continued rejection.
- The prompt and metrics tool explicitly identify unavailable expense, EBITDA, profit-margin, cash-flow, and attendance data. A narrow validation guard additionally catches explicitly labeled numeric EBITDA/profit-margin assertions. It is not a comprehensive semantic validator.
- Retrieval separately searches the selected center report and applicable shared guidance. It prioritizes director observations, enriches the guidance query with those observations, and reserves three of six slots for each evidence type. This recovered the previously omitted capacity and discount-policy evidence. Scores from different queries should not be compared as a single global ranking.
- Evaluation errors now record safe first-party validation codes, and the interface distinguishes an unverifiable answer from a connection/configuration problem.

The new live run did not need a repair attempt: all 30 initial answers passed validation. Local scripted tests exercise the bounded repair path. The local suite has 33 tests: 32 passed together before the final interface-message test was added, and the five interface tests then passed with that new case.

## Qualitative checks and remaining limits

Codex reviewed the eight combined answers and four boundary answers from the new run. This is assistant review, not independent human review.

- Both previously failing cases now complete. The EBITDA answer correctly declines to calculate unavailable profit metrics and explicitly distinguishes revenue from EBITDA.
- Combined answers use three next steps, and the grouped-citation export problem is resolved.
- The cross-center request returns no other-center figures; the exact vacancy-loss question acknowledges that the causal amount is unknown.
- `mix_08` still speculates about enrollment and attendance fluctuations even though attendance is unavailable. This is an unsupported inference that passed the narrow automatic screens.
- `mix_02` proposes family payment status as a possible revenue factor even though this prototype models earned tuition, not collections. It also makes an insufficiently supported claim about what enrollment changes alone explain.
- `boundary_04` refuses the unselected period but still suggests selecting a period unavailable as a completed week. The response could explain the date limitation more clearly.
- Some action items and causal statements need closer claim-by-claim citation review. Valid source IDs establish provenance, not that the passage supports each sentence.

The remaining issues should be evaluated on additional unseen questions and reviewed by an operations/finance subject-matter expert before an internal pilot. The current changes address the approved citation, retrieval, and completion failures; they do not establish production readiness.
