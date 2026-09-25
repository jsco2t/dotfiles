# Rep scorecard / leaderboard — from the `Hygiene Run` object

**Source of truth:** HubSpot custom object **`Hygiene Run`** — objectTypeId **`2-63704277`** (`p22461953_hygiene_run`,
portal 22461953). One record per rep per run. The rep skill (and on-demand manager runs) write these; this skill reads them.

## 0. Reading the custom object (and what to do if it's blocked)
Search `Hygiene Run` by objectTypeId **`2-63704277`** (or `p22461953_hygiene_run`) — the records are searchable server-side.
**If the connector returns nothing / "not exposed":** the usual cause is the object's **connector/search-access setting** —
have an admin enable it in **Settings ▸ Objects ▸ Hygiene Run** (object setup settings), then re-run; the board then renders
in chat from §1–§5. If that toggle is off and can't be enabled in-session, **don't fail or fabricate**: (a) point the manager
to the **HubSpot native list view** (CRM ▸ Hygiene Runs, sort by `committed_at_risk_usd`), and (b) build a **current snapshot
via on-demand scoring** (§6), labeled as fresh (not the stored trend).

## 1. Read the records (when the object is accessible)
Pull `Hygiene Run` records (object `2-63704277`) — recent window (e.g. last 60–90 days), these properties:
`run_label, run_id, rep_owner_id, rep_name, run_ts, score, score_prev, score_delta, deals_scanned,
weighted_pipeline_usd, issues_critical, issues_warning, issues_info, issues_fixed, outstanding_count,
max_days_outstanding, avg_days_outstanding, open_over_30d, repeat_offenders, feedback_count,
committed_at_risk_usd, quarter_at_risk_usd, overdue_at_risk_usd, pipeline_at_risk_usd, total_at_risk_usd, risk_pct, meddpicc_thin`.
Group by `rep_owner_id`; take the **latest** by `run_ts` as the rep's current state; keep prior runs for trend (rolling
avg of the last 4). Resolve `rep_owner_id` → name via the record's `rep_name` (or `search_owners`).

## 2. Two numbers per rep — lead the view by audience
Each `Hygiene Run` carries a **Hygiene score** (0–100, rep accountability) **and** a **forecast-risk $** (on forecasted
deals only — COMMIT/BEST_CASE; OMIT/CLOSED excluded). They answer different questions and often diverge — surface both.

**The leaderboard (one row per rep):**
| Rep | Hygiene | Δ | **Committed @risk** | **This-Qtr @risk** | Overdue | Pipeline | Risk % | Crit/Warn |
- **Hygiene** = latest `score`; **Δ** = `score_delta`.
- **Committed @risk** = `committed_at_risk_usd` — at-risk $ on **COMMIT-category** deals (what reps are committing to the number). The sharpest leadership signal.
- **This-Qtr @risk** = `quarter_at_risk_usd` (forecasted deals closing this quarter, unhealthy). **Overdue** = `overdue_at_risk_usd` (past close date). **Pipeline** = `pipeline_at_risk_usd` (later).
- **Risk %** = `risk_pct` (total ÷ forecasted ARR).
- **Rank two ways:** coaching → **Hygiene ascending**; leadership triage → **Committed @risk** (or **This-Qtr @risk**) **descending**.
- A rep with **no record** → **"no run yet"**; never fabricate — offer "score now?".
- **Forecast-at-risk threats now include the close<->stage coherence flag (D-40)** alongside dark / stalled / stale-next-step / thin-MEDDPICC: an early-stage deal with an imminent close, or any deal past its close date, raises the at-risk columns.

## 3. Cadence (expected: weekly)
`days_since = today − run_ts`. **On-time** ≤7d · **Late** 8–14d · **OVERDUE** >14d · **NEVER** (no record). Flag Late/Overdue/Never.

## 4. Team summary
- **Risk (headlines):** total **Committed-at-risk $** (COMMIT category) + **This-quarter-at-risk $**; flag **Overdue** if any; top offenders by each. (% vs forecasted ARR — OMIT/CLOSED excluded.)
- **Hygiene:** team avg score + trend; **# reps overdue / never run**; total outstanding + open >30d.
- **Coaching call-outs:** declining hygiene (`score_delta < 0`), chronic overdue cadence, repeat offenders, biggest committed-at-risk.

## 5. Audience views (same data, tailored depth)
- **RevOps (Tabatha):** both numbers + systemic/data-integrity + coverage + feedback themes (full table).
- **VP Sales (Ramesh):** lead with **Committed-at-risk** (COMMIT deals) + **This-quarter-at-risk** — the deals to chase, by rep and by deal; hygiene as the coaching layer.
- **Revenue Leadership (Bjorn):** one screen — **Committed-at-risk $** + **This-quarter-at-risk $**, team avg hygiene + trend, cadence compliance %, top-3 exposures.

## 6. On-demand scoring + MEDDPICC verification (when records are sparse/stale, or to check qualification)
If a rep has no record, a stale one, or the manager asks to "score <rep>" / "verify <rep>'s MEDDPICC": run the hygiene
engine **scoped to that owner** (bulk pull → `checks.md` + `meddpicc_rubric.md` + `corrections.md` suppressions → score per
`run_record.md`), **then run the MEDDPICC evidence verification** (`meddpicc_verification.md`) on the rep's forecasted/top
deals — cross-check each claim against Fathom/email/notes/public-Slack, credit only evidenced qualification, flag
unsupported/contradicted fields. Present a **fresh in-chat snapshot** (label it as current, not the stored trend) — **do not
write the object**; the twice-daily batch is the authoritative writer. Read-only on the deals. One rep at a time (bounded
per-owner pull); never loop/cycle. The team = iterate the reps deliberately (confirm scope first). Log which deals were not verified.

## 7. Scoring explainer (include a short version in every board; full version on request)
Reps and leaders should see *why* a number is what it is. The hygiene score (0–100, **Variant B**) = **Cleanliness (80)**
+ **Cadence (20)**:
- **Cleanliness (80):** `80 × cap/(weighted_open+cap)` — a saturating curve where each open issue weighs `severity × aging`
  (CRITICAL 5 / WARNING 2; aging `<7d ×1`, `≥7d ×2`), `cap = max(deals,4)×5`. A clean book → 80. **Fixing any issue raises
  the score immediately.**
- **Cadence (20) — coverage-graded:** `20 × coverage`, coverage = your open deals **worked in the last 14 days** ÷ total open deals (a real edit via the HubSpot UI or the Claude skill, or a logged contact; excludes HubSpot's AI scorer + the batch). Rewards tending your *whole* book; graded, fair across book sizes. Orthogonal to Cleanliness (working a deal ≠ it being healthy).
- A clean book = **100**. There is **no Resolution component** (the old all-or-nothing 30-pointer was folded into
  Cleanliness — see `run_record.md` / `DECISION_LOG` D-22). Stall thresholds are recalibrated for long-cycle deals
  (Disc 120/Qual 90/Val 75/Prop 45/Proc 30/Pend 21).
- The forecast-risk $ is **separate**, on forecasted deals only (COMMIT/BEST_CASE). To raise the hygiene score: clear open
  issues (re-engage dark accounts, advance/re-stage stalled deals, fill thin MEDDPICC, freshen next steps, set a realistic close date on early-stage/overdue deals (close<->stage coherence, D-40)). Full model in `run_record.md`.

## 8. Principle 0
Every score/number cites its `Hygiene Run` record (`run_id` + `run_ts`) or, for an on-demand run, the live deal/field it
was computed from; every MEDDPICC verdict cites its evidence (or the on-record empty search). Do not invent a score for a
rep with no data. Present in chat (no HTML/artifacts) unless an export is requested.

## 9. Closed-lost integrity & on-hold legibility (read-only, D-42 — never score-affecting)
The hygiene score sees only the OPEN book, so it can RISE when a rep **writes dead deals off** or pads the book with
"on hold" deals. Surface these for honesty (cite the deals; do NOT change the score):
- **Pipeline written off this period (item 1b):** sum + count of the rep's deals moved to **Closed Lost within 30 days**
  (`is_recent_close_lost`, `CLOSE_LOST_WINDOW`). Show beside a rising score so a closure-driven jump is legible
  (e.g. "score +17, but $1.49M / 5 deals written off this window").
- **Missing loss reason (item 2):** recently-closed-lost deals with an empty `closed_lost_reason` — a RevOps/coaching
  line (out of rep-score scope).
- **Same-customer recreate (item 3):** a deal moved to Closed Lost **while an OPEN deal exists on the same company**
  within the window — keyed on **company ID, never deal name** (`recreate_candidates`); pressure-test whether the loss
  was real or just re-papered.
- **On-hold share (item 7d):** "X of N open deals on hold (Y%)" (`on_hold_share`) — a book that is mostly "on hold"
  (its dark/stalled flags suppressed) is visible, not silently rewarded.
> The **score-CHANGING** variants (excluding recent write-offs from positive score contribution; a new-deal cap-padding
> guard) are **GATED pending review** (ROLLOUT_FEEDBACK_DAY1 items 1a/1c/7c) — surface, don't penalize, until approved.

## 10. Channel / partner sibling-deal warnings (`scorecard_data.sibling_deal_warnings`)
The batch computes `sibling_deal_warnings` in `scorecard_data` when the same partner (reseller / distributor) appears on
**multiple open deals with distinct end customers** owned by the same rep. This is a **read-only / coaching signal** — it
indicates a risk of cross-contamination (activity or recommendations for partner X bleeding across two deals that share that
partner but serve different end customers). Surface it as follows:

- Read `scorecard_data.sibling_deal_warnings` (from the latest `scorecard_data_*.json`). Each entry names the **partner**,
  the **deals** it spans, and the **distinct end customers** involved.
- Coach the rep: "Partner \<X\> is active on both \<Deal A\> (EC: \<A\>) and \<Deal B\> (EC: \<B\>). Keep each deal's
  outreach and next-step activity scoped to its own end customer — no cross-pollination."
- **No writes.** The manager skill does not modify deals, contacts, or Hygiene Run records in response to this signal. It
  is advisory only. The rep resolves scope by reviewing each deal card and keeping activity distinct.
- If a deal in the warning also carries `resolver_pending: true` in the rep's report, flag it explicitly: the resolver has
  not yet run, so the rep's recommendation bundle may include emails belonging to the sibling deal — the rep should apply
  extra scrutiny before acting on that deal's next step.