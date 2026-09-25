# MEDDPICC depth rubric (score the TEXT, not the checkbox)

> **⚠️ Enforced source of truth = the live engine** (`deal-hygiene/lib/ciq_rules.py:245-260`). The depth scale
> below is a COACHING aid, not the flag mechanism. A field is *flagged thin* when it is **hollow** per the engine:
> empty/<3 words; `metrics_v2` without a number/$/%/timeframe; `decision_process_v2` without authority/approval
> language; `paper_process_v2` without a paperwork term; `decision_criteria__cloned_` under 5 words. Required by
> stage: **Discovery** = Identify Pain only · **Qualified** = Pain/Metrics/Decision Criteria/Decision Process ·
> **Validate+** = all 5. Severity: Qualified ≥3 hollow = CRITICAL; Validate+ ≥2 hollow = CRITICAL; otherwise
> WARNING. Full Standard-vs-Floor explanation: `docs/playbooks/ciq-sales-qualification-playbook.md`.

Qualification is judged on the **content of the MEDDPICC text fields**, not on whether the Champion/EB
calculated fields are populated (those come from contact labels — see corrections.md).

## Depth score (0–10) per field
- 0 — empty
- 2 — a phrase, no substance ("save money," "John Smith")
- 4 — a sentence with some specificity
- 6 — specific with names / numbers / dates
- 8 — comprehensive: context + ownership + timeline
- 10 — could be read straight into a forecast review

**Judge SUBSTANCE, not length.** Look for each field's defining signal: `metrics` → a quantified target
(number / $ / % / timeframe); `decision_process` → named roles / approvers / steps; `paper_process` →
PO / MSA / legal / procurement; `decision_criteria` → concrete requirements; `identified_pain` → a stated
business problem. A long but vague field is still thin; a short but specific one is fine. Flag only what's
empty or genuinely below its stage bar — never penalize on character count.

## Stage thresholds (coaching target; the enforced floor is the engine marker above)
| Field (HubSpot) | Discovery | Qualified | Validate | Propose | In Proc | Pending |
|---|--|--|--|--|--|--|
| Identified Pain (`identified_pain_v2`) | 4 | 6 | 7 | 8 | 8 | 8 |
| Metrics (`metrics_v2`) | — | 4 | 6 | 8 | 8 | 8 |
| Decision Criteria (`decision_criteria__cloned_`) | — | 4 | 6 | 8 | 8 | 8 |
| Decision Process (`decision_process_v2`) | — | 4 | 6 | 8 | 8 | 9 |
| Paper Process (`paper_process_v2`) | — | — | 4 | 7 | 8 | 9 |

*Note: "—" = not required by the engine at that stage. Metrics/Criteria/Process are only engine-required from Qualified onward; all 5 fields are engine-required from Validate onward.*

- **Engine CRITICAL rule (authoritative):** Qualified with ≥3 hollow fields = CRITICAL; Validate+ with ≥2 hollow fields = CRITICAL; otherwise WARNING.
- **Discovery:** only `identified_pain_v2` is engine-checked; hollow (empty/<3 words) → WARNING.
- The **named buyer/decision-maker often lives in `decision_process_v2` text** even when `economic_buyer_v2`
  (the label field) is empty — so read the text before concluding "no buyer."

## What strong looks like (targets for drafted updates)
- **Pain:** "RHEL renewal Apr 2026, 4,000 nodes @ $550/node ($2.2M); CFO cost mandate post-Q3 layoffs; needs binary compat + 24×7 + FIPS subset."
- **Metrics:** "$1.54M/yr savings (70% off $2.2M); payback <6mo incl. $180K migration."
- **Decision Process:** "John (architect) recommends → Mike (CTO) tech sign-off (done Dec 1) → Sarah (CFO) budget by Dec 22 → procurement 2–3wk; compelling event Apr 30 expiry."

When a field is below threshold, draft an update that reaches the **stage threshold** (not 10), pulled from
the deal's conversations/emails. If the source doesn't contain it, surface it as a question for the rep's
next customer interaction — never fabricate.
