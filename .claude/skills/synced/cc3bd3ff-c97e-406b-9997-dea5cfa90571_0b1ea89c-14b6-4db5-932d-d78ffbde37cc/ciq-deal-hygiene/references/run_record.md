# Run record, hygiene score & feedback (feeds the accountability log — leadership view)

Every run emits one standardized record at the end of Phase 6, so leadership can track across runs and reps:
**cadence** (how often each rep runs), **what's outstanding and for how long** (aging), **what failed**, a
**score that trends over time**, and any **rep feedback** caught during the run. The record is deterministic from
HubSpot ground truth — re-running recomputes the same values (it can't be gamed except by actually fixing issues).

## Two-layer architecture (who writes what)
Two writers, two layers — kept consistent because the score is a deterministic function of live deal fields:
- **Layer A — the server-side hygiene batch (the authoritative writer).** A scheduled job (`score_all_reps.py`, Windows
  Task Scheduler, **2×/day**) scores every rep, **writes the `Hygiene Run` records** (rep-level rollup + `score_delta`
  trend), stamps each deal's `hygiene_score`/`last_hygiene_score_date`, and emits the **differential report**. Reps and
  managers **cannot** write the `Hygiene Run` custom object via the connector — this batch is the only writer.
- **Layer B — the rep skill (operational).** Reps fix their own deals (Next Step, MEDDPICC, labels, line items,
  `blockers`). Since v4.6 (D-52) it does **NOT** stamp `hygiene_score`/`last_hygiene_score_date` — both stamps are
  batch-owned (Layer A stamps every open deal each run); a fix is confirmed by the next report's "Since the last
  report" section rather than a skill-side recompute. The rep skill never writes the object.
- **Layer C — the manager skill.** Reads the records (Layer A) for the leaderboard, and **verifies MEDDPICC against
  evidence** (Fathom/email/notes/Slack) — read-only.

**Why nothing drifts:** the per-deal `hygiene_score` is a pure deterministic function of the deal's live fields, so any
writer running the shared rubric on the same data computes the same value (idempotent — no overwrite conflict). The
rubric lives in ONE place (this file + `checks.md`); `last_hygiene_score_date` tracks freshness. Layer A computes the
object rollup and the per-deal scores in the **same pass from the same data**, so the two are coherent by construction.

## Per-deal `hygiene_score` (the deal-level property, 0–100)
Each open Sales deal carries its OWN cleanliness score (distinct from the rep-level book score below): a saturating curve
`hygiene_score = round(100 × cap / (deal_weighted_open + cap))` with **cap = 10**, where `deal_weighted_open = Σ(severity ×
aging)` over that deal's open flags (severity `CRITICAL 5 · WARNING 2 · INFO 0.5`; aging **`<7d ×1 · ≥7d ×2`, capped at ×2** — matches the batch's `aging_mult`; there is NO ×3 tier).
Clean deal → 100; `weighted_open=10` → 50; `=30` → 25. Written by Layer A ONLY (every deal, each run; v4.6/D-52 —
Layer B no longer writes it). `last_hygiene_score_date` = the date the batch last computed it.
**Scored flags (the ONLY things in `deal_weighted_open`):** dark · stalled · stale-next-step · thin-MEDDPICC · close<->stage coherence (D-40) (+ line-item/ARR
gaps). **`blocker uncaptured` is ADVISORY, NOT scored** — surface it as "set the `blockers` field," but it does not add to
`deal_weighted_open` (the batch never penalizes an empty `blockers`; the field only matters as a hold-until date that
*suppresses* flags). Don't let it lower a deal's score. **Close<->stage coherence (D-40) IS scored here** (CRITICAL early-stage-imminent, WARNING overdue) AND joins the **forecast-threat set** (dark / stalled / stale-next-step / thin-MEDDPICC + close-coherence) -> it raises forecast-at-risk.

## Record (one per run)
```json
{
  "run_id": "<timestamp-or-uuid>",
  "rep_owner_id": "<hubspot owner id>",
  "rep_name": "<resolved name>",
  "run_ts": "<ISO-8601>",
  "pipeline": "45314112",
  "deals_scanned": 0,
  "priority_set_size": 0,
  "weighted_pipeline_usd": 0,
  "issues_found": { "critical": 0, "warning": 0, "info": 0, "by_type": { "<check>": 0 } },
  "issues_fixed_this_run": 0,
  "issues_failed": 0,            // ⚠️ attempted-not-confirmed
  "needs_rep_input": 0,          // 🙋
  "revops_handed": 0,            // vestigial — all items are rep-owned now (kept for schema compatibility)
  "not_deep_swept": ["<deal_id>"],
  "outstanding": [
    { "deal_id": "<id>", "deal": "<name>", "check": "<type>", "severity": "CRITICAL|WARNING|INFO",
      "owner": "you", "first_seen": "<ISO date>", "days_outstanding": 0 }
  ],
  "score": 0, "score_prev": null, "score_delta": 0,
  "coverage_complete": true, "coverage_gaps": 0,
  "coverage": [
    { "deal_id": "<id>", "company_swept": true, "line_items_pulled": true, "domain_matched": true,
      "fathom_checked": true, "email_pulled": true, "slack_checked": true }
  ],
  "feedback_count": 0,
  "feedback": [
    { "feedback_id": "<uuid>", "ts": "<ISO-8601>", "deal_id": "<id|null>", "deal_name": "<name|null>",
      "check": "<check or 'general'>",
      "feedback_type": "false_positive|false_negative|wrong_value|wrong_owner|missing_evidence|threshold|ux|other",
      "skill_output": "<what the skill claimed, verbatim>", "rep_correction": "<rep's exact words / correct value>",
      "proposed_rule_change": "<skill-drafted fix>", "evidence": "<recording id / email / field>",
      "severity": "blocker|major|minor", "status": "new", "skill_version": "v1.x" }
  ]
}
```

## Per-deal coverage (anti-skip — records that the required pulls actually ran)
For every deal judged, record whether each mandatory pull ran: `company_swept` (End-Customer company `notes_last_contacted`),
`line_items_pulled`, `domain_matched`, `fathom_checked`, `email_pulled`, `slack_checked` (true / false / "n/a"). Set
`coverage_complete = false` and `coverage_gaps = N` if any deal is missing a mandatory pull (company / line-items / domain).
**A run with `coverage_complete = false` is not trustworthy — go complete the missing pulls before presenting.** This is the
backend proof that replaces a printed evidence template; the rep-facing output format stays flexible.

## Aging — how long each issue has been open
Each outstanding issue is keyed by `(deal_id, check)`. On every run, read the rep's **prior record** first:
- already open last run → carry its `first_seen`; `days_outstanding = today − first_seen`;
- new this run → `first_seen = today`;
- previously open, now clear → drops off (counts toward fix-rate).
Report **max & average days-outstanding** and the **count open >30d**. A `(deal_id, check)` open across N+ runs is a **repeat offender**.

## Hygiene score (0–100 — deterministic, explainable) — **Variant B (2026-06-06)**
**Two components** (every open issue counts — all flagged items are the rep's):
- **Cleanliness (80):** `80 × cap / (weighted_open + cap)` — a **saturating** curve (never floors, always
  differentiates), where each open issue weighs `severity × aging` — severity `CRITICAL 5 · WARNING 2 · INFO 0.5`,
  aging **`<7d ×1 · ≥7d ×2`** (multiplier capped at ×2 so one ancient deal can't dominate) — and `cap = max(deals,4) × 5`
  (normalizes for book size, with a small-book floor). A clean book → 80; issues drive it asymptotically toward 0.
  **Fixing any issue raises the score immediately** (it lowers `weighted_open`), so the score tracks current cleanliness
  with no lag and no separate component to game.
- **Cadence (20) — coverage-graded:** `20 × coverage`, where `coverage = (your open deals with real activity in the last
  14 days) ÷ (total open deals)`. "Real activity" = a tracked field changed (next step, stage, close date, MEDDPICC,
  champion/EB, blockers) **or a logged customer contact**, from a genuine source — **`CRM_UI`** (manual) or the **Claude
  connector** (the rep's per-user app service account, i.e. edits made through the skill) or a logged contact — *excluding*
  HubSpot's AI deal-scorer (`AI_GROUP`) and the scoring batch's own writes. So it rewards tending your **whole book**
  (graded 0–20), is fair across book sizes (a %), and is hard to game with one token edit. (Streak/consistency over time is
  a future v2, once run-history accrues.)
`score = round(cleanliness + cadence)`, clamped 0–100. `score_delta = score − score_prev`. A clean, fully-worked book = 100.
**Cadence and Cleanliness are deliberately orthogonal:** cadence = *are you working the book*, cleanliness = *is it healthy*.
A deal can be "worked" (touched via the skill) yet still flagged (e.g. MEDDPICC updated but customer not contacted) — it
earns cadence but still costs cleanliness.

> **Why no Resolution component (changed from the earlier 50/30/20 model):** the old Resolution(30) was all-or-nothing in
> the read-only batch — any open issue → 0 — which crushed every non-clean rep by 30 points and didn't differentiate them.
> Folding it away (Cleanliness 50→80) removes that cliff; cleanliness already rewards fixing. See `DECISION_LOG.md` D-22.

**Stage-stagnation thresholds (recalibrated for long-cycle deals):** Discovery 120 · Qualified 90 · Validate 75 ·
Propose 45 · In Procurement 30 · Pending Approval 21 (days in stage). Over the threshold = "stalled."

**MEDDPICC is scored by CONTENT, not length.** A field is *thin* only when it lacks its defining substance — `metrics`
with no number/$/%/timeframe, `decision_process` with no named role/approver/step, `paper_process` with no
PO/MSA/legal/procurement, `decision_criteria` with no real requirements, `identified_pain` empty. In the **rep's own run**
the model reads each field against the rubric and the rep can dispute; the batch applies these markers deterministically.
Never score MEDDPICC by character count.

## Forecast risk ($ — graded, on FORECASTED deals only; the leadership-triage number)
Computed only on deals you're **actually forecasting** — `hs_manual_forecast_category` in **COMMIT** or **BEST_CASE**.
**OMIT and CLOSED are excluded** (an omitted deal isn't in the forecast — its mess still hits the *hygiene* score, not risk). Per deal:
`risk_$ = ARR × health_deficit × forecast_weight`
- **health_deficit (0–1):** worst open issue — critical / dark >60d / next-step >30d / MEDDPICC-critical → **1.0**;
  dark 30–60d / stalled → **0.6**; any warning → **0.3**; clean → 0.
- **forecast_weight:** by stage (Discovery .2 · Qualified .4 · Validate .7 · Propose+ 1.0); bumped to **≥0.9** for
  COMMIT-category, overdue, or this-quarter deals. Use **ARR** (the deal's own probability is suspect).
- **Buckets:** `committed_at_risk_usd` = at-risk $ on **COMMIT-category** deals (the headline; overlaps the timing buckets).
  **Timing (exclusive, sum to `total_at_risk_usd`):** `overdue_at_risk_usd` (closedate < today) · `quarter_at_risk_usd`
  (today ≤ closedate ≤ current-quarter end) · `pipeline_at_risk_usd` (later or no close date). *Current-quarter end = the
  CIQ fiscal quarter end (FY26: Q1 Apr 30 · Q2 Jul 31 · Q3 Oct 31 · Q4 Jan 31 — derive from today, see `reference_data.md`).*
- `risk_pct = total_at_risk ÷ forecasted ARR` (Commit + Best Case). **Committed** and **This-quarter** are the leadership headlines; hygiene is rep accountability.

## Rep feedback (interim path — the deal's `hygiene_feedback` property, NOT the object)
Reps can't write the `Hygiene Run` object, so the `feedback[]` array above is what the **batch** can record; the **rep
skill** captures disputes by **appending a JSON item to the deal's `hygiene_feedback` property** (read → parse array →
append → write; never overwrite — see `fix_playbook.md` → Feedback). Each item: `ts, skill_version, feedback_type,
check, skill_output (verbatim), rep_correction (verbatim), evidence, status:"new"`. RevOps parses `hygiene_feedback`
across deals; a **skill-improvement agent** triages them into proposed `corrections.md` / `checks.md` edits —
**verified against ground truth + human-confirmed** before they ship (a rep can be wrong too — Principle 0). The rep
never fills a form. *(This is the interim capture until the scalable feedback architecture/infra is decided.)*

## What the accountability log shows (leaderboard / trend)
Per-rep **score over time** (improving/declining via `score_delta` + rolling 4-run average), **cadence compliance**
(who isn't running it), **outstanding aging** (oldest unresolved), **failure rate** (⚠️), **repeat offenders**, and
**feedback themes** (clustered `feedback_type` + `check`).

## Where it's deposited — `Hygiene Run` object `2-63704277` (LIVE) — **written by the Layer-A batch**
The **server-side hygiene batch** (Layer A, above) creates **one record per run** in the live custom object —
**objectTypeId `2-63704277`** (`p22461953_hygiene_run`, portal 22461953). Append-only: one record per run; never overwrite.
**The rep and manager skills do NOT write this object** (the connector can't create custom-object records) — they read it.
The batch maps the run record → object properties:

| Object property | Value |
|---|---|
| `run_label` | `<rep_name> — <YYYY-MM-DD> — <score>` (primary display) |
| `run_id` · `rep_owner_id` · `rep_name` · `run_ts` | from the run envelope (set `rep_owner_id` so the leaderboard groups by rep) |
| `deals_scanned` · `priority_set_size` · `weighted_pipeline_usd` | run envelope |
| `issues_critical` · `issues_warning` · `issues_info` | `issues_found.*` |
| `issues_fixed` · `issues_failed` · `needs_rep_input` · `revops_handed` | counts |
| `outstanding_count` · `max_days_outstanding` · `avg_days_outstanding` · `open_over_30d` · `repeat_offenders` | aging |
| `score` · `score_prev` · `score_delta` | hygiene score (above); see prior-run note |
| `committed_at_risk_usd` (COMMIT fcat) · `quarter_at_risk_usd` · `overdue_at_risk_usd` · `pipeline_at_risk_usd` · `total_at_risk_usd` · `risk_pct` | forecast risk on forecasted deals (Commit+Best Case); committed = COMMIT category; timing buckets; % vs forecasted ARR |
| `meddpicc_thin` | # deals with a thin MEDDPICC field (content markers) |
| `feedback_count` · `feedback_blockers` | from `feedback[]` |
| `coverage_complete` (1/0) · `coverage_gaps` | coverage |
| `payload_json` · `feedback_json` · `coverage_json` | the full arrays serialized as JSON strings |

**`score_prev` / `score_delta`:** before writing, read the rep's most recent prior `Hygiene Run` (search object
`2-63704277` filtered `rep_owner_id = <id>`, sort `run_ts` desc, limit 1); `score_prev` = its `score`,
`score_delta = score − score_prev` (null/0 on first run). Reps need *create* permission on the object (admin grants).
(See `accountability/hygiene_run_object.md` for the schema.)
