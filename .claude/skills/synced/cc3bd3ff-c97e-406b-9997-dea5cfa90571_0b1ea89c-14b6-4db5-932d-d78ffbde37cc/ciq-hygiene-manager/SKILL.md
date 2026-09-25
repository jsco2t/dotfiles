---
name: ciq-hygiene-manager
description: Manager / leadership view of CIQ deal-hygiene — a rep SCORECARD and team accountability rollup for sales managers (Tabatha / Ramesh / Bjorn). Reads the Hygiene Run records to rank reps by hygiene score, trend, cadence, outstanding aging, and repeat offenders; can score any rep on demand AND verify MEDDPICC against the actual evidence (Fathom calls, email bodies, notes, public Slack) to catch qualification that is written but not backed by anything real. Use when a manager says "team hygiene", "rep scorecard", "/team-hygiene", "how are my reps doing", "score the team", "score a rep by name", "who's behind on hygiene", "a specific rep's hygiene", "verify the MEDDPICC", "is this deal really qualified", or "explain the scoring". Read-only on reps' deals (managers coach; the rep skill applies fixes). Portal 22461953, FY26, Sales pipeline.
---

# CIQ Deal Hygiene — Manager / Leadership (team scorecard)

For **Tabatha** (RevOps), **Ramesh** (VP Sales), **Bjorn** (Revenue Leadership). This is the leadership view: rank the
team by hygiene, see who's slipping or overdue, and drill into a rep — **read-only on reps' deals.** Managers coach and
track; they do **not** fix reps' deals (that's the rep's own `ciq-deal-hygiene` skill).

## What you need connected
- **HubSpot** (required) — the `Hygiene Run` records + deals.
- **Fathom / Slack** (optional) — only for drilling into a specific rep's deals.

**Data access (read this first).** Search the **`Hygiene Run`** object directly by its objectTypeId **`2-63704277`**
(or fully-qualified `p22461953_hygiene_run`) — the records are searchable server-side. If the connector returns nothing /
"not exposed", the fix is almost always a **HubSpot object setting**: enable the object's **connector/search access in its
object setup settings** (Settings ▸ Objects ▸ Hygiene Run), then re-run. Only if that's off and can't be enabled in-session,
**do NOT fail or fabricate a board** — instead:
1. point the manager to the **HubSpot native list view** of the object (**CRM ▸ Hygiene Runs**, sorted by
   `committed_at_risk_usd`) for the stored leaderboard + trend — that's the canonical board today; and
2. offer a **current snapshot via on-demand scoring** (live deal data) — one rep at a time (bounded); the full team is heavy.
The guaranteed programmatic read + trend path is the CIQ Hygiene **backend / MCP server** (reads the object server-side).

## What it does
1. **Rep scorecard / leaderboard (default).** Read the `Hygiene Run` custom object and rank every rep by score, trend,
   cadence, open issues, and aging — plus a team summary and coaching call-outs. See `references/scorecard.md`. The
   records are produced by the **twice-daily server-side hygiene batch** (the authoritative writer of the object — reps
   can't write it via the connector), so current records should always exist.
2. **Verify MEDDPICC against the evidence (the anti-gaming layer — manager-only).** The rep skill scores MEDDPICC by
   content markers (catches *empty/thin*); this skill goes further and **verifies each populated MEDDPICC claim against
   Fathom calls, email bodies, deal/contact notes, and public Slack** — crediting only qualification the record actually
   supports, and flagging populated-but-**unsupported** fields (the gaming case) or **contradicted** ones. Bounded to a
   rep's forecasted/top deals, one rep at a time. See `references/meddpicc_verification.md`.
3. **Score / drill on demand.** For a named rep, run a fresh hygiene pass scoped to that owner (same engine as the rep
   skill — `references/checks.md` + `meddpicc_rubric.md`) **plus the MEDDPICC evidence verification (#2)**, and present
   the score + the specific deals driving risk with coaching guidance. **Read-only — never fix-it-now here** (managers
   coach; the rep's skill applies fixes). The durable `Hygiene Run` record comes from the scheduled batch; an on-demand
   run is a fresh in-chat snapshot (label it as such), not a write.
4. **Explain the score.** On "explain the scoring" / "how does a rep get to 100", lay out the model from
   `references/run_record.md` — **Variant B: Cleanliness (80) + Cadence (20)**, no Resolution; forecast-risk is separate —
   in plain terms; include a short version in every scorecard so a rep reading their number knows what moves it (fixing
   any open issue raises it immediately).

5. **Closed-lost integrity (write-off legibility - D-42).** The hygiene score only sees the OPEN book, so a rep can lift it by **writing dead deals off** (Closed Lost shrinks the book). On request, surface - read-only, **never score-affecting** - the recently-closed-lost picture per rep (within 30d): **(1b)** "pipeline written off this period: $X / N deals" beside the score; **(2)** closed-lost deals with an empty `closed_lost_reason`; **(3) same-customer recreate** - a deal moved to Closed Lost while an OPEN deal exists on the **same company** within the window (company-ID keyed, `recreate_candidates`); and **(7d)** the **on-hold share** ("X of N open deals on hold, Y%") so a book mostly "on hold" is visible, not silently rewarded by suppression. Cite the deals. See `references/scorecard.md`. *(ROLLOUT_FEEDBACK_DAY1 items 1b/2/3/7d; the score-CHANGING variants - excluding write-offs from the score, a cap-padding guard - remain GATED pending review.)*

## Flow
### Default — the team scorecard
Read the `Hygiene Run` object (objectTypeId **`2-63704277`**) per `references/scorecard.md`: latest record per rep +
prior runs for trend. Produce the **leaderboard** (ranked, lowest/most-at-risk first), the **team summary**, and
**coaching call-outs** (declining score, overdue cadence, repeat offenders, biggest aged-open risk). Tailor depth to the
audience (below). Cite each number to its `Hygiene Run` record (`run_id`/`run_ts`). Reps with no record show **"no run yet — score now?"** — never fabricate a score.

### "Score <rep>" / "Score the team"
Resolve the owner(s) (by name/email → `hubspot_owner_id`). For each rep: run the hygiene checks **scoped to that owner**
(bulk pull → checks per `checks.md` → score per `run_record.md`), **then run the MEDDPICC evidence verification**
(`references/meddpicc_verification.md`) on that rep's forecasted/top deals — cross-check each populated MEDDPICC claim
against Fathom calls, email bodies, notes, and public Slack; credit only evidenced qualification and flag
unsupported/contradicted fields. Read-only on the deals — surface findings, don't fix. Present it as a **fresh in-chat
snapshot** (the durable, trended `Hygiene Run` record is written by the scheduled batch — this skill does not write the
object). For "the team," do reps **deliberately** (confirm scope; each rep is a separate bounded pull — never loop/cycle).

### "Drill into <rep>"
Show that rep's latest `Hygiene Run` + their **outstanding items with aging** + the specific deals (stage, weighted value,
the cited flag) + coaching notes (what to work, what's slipping) + the **MEDDPICC verification verdicts** (verified /
unsupported / contradicted, each with cited evidence — `meddpicc_verification.md`). No fixes — hand the rep their own skill for that.

## Audience tailoring (same data, different depth)
- **Tabatha (RevOps):** full detail — data-integrity, coverage, systemic/account items, the complete table.
- **Ramesh (VP Sales):** forecast-risk + coaching — weighted pipeline on stalled/dark deals, who needs coaching, top at-risk deals.
- **Bjorn (Revenue Leadership):** one-screen summary — team avg score + trend, cadence compliance, top-3 risks.

## Golden rules
1. **Read-only on reps' deals.** Never apply fixes — that's the rep's `ciq-deal-hygiene` skill. You coach and track. This skill also does **not** write the `Hygiene Run` object — the scheduled batch owns that.
2. **Principle 0 — cite or don't claim.** Every score/number cites its `Hygiene Run` record (`run_id`/`run_ts`) or the live deal/field it was computed from. Never invent a score for a rep with no data — show "no run yet." **For MEDDPICC verdicts, never call a field "gamed/unsupported" without an on-record empty search** — cite the evidence, or cite which sources you searched and found nothing.
3. **Verify MEDDPICC against evidence — don't trust prose.** A populated MEDDPICC field earns qualification credit only when Fathom/email/notes/Slack corroborate it (`meddpicc_verification.md`). Unsupported = treated as thin; contradicted = a critical flag.
4. **Consistent scoring.** The score model + object are identical to the rep skill (`references/run_record.md`) — don't redefine them. Be ready to **explain the model** plainly on request (how a rep reaches 100).
5. **Partner / channel deals — read the score in context.** Reps working through partners (channel/embedded/OEM) often can't control engagement cadence or always see customer-side activity; their hygiene/risk can read worse for reasons outside their control. Note this when it applies — the score reflects record completeness, not effort. (DD-11)
6. **Chat-only** (no HTML/artifacts) unless a manager explicitly asks for an export.
7. **Don't cycle.** On-demand scoring + verification is a bounded per-owner pull (one rep at a time); fix a failed query once, then report — never loop. Log which deals you did **not** verify so coverage is honest.

## Reference files
- `references/scorecard.md` — the leaderboard/trend spec + how to read the `Hygiene Run` object + audience views + the scoring explainer.
- `references/meddpicc_verification.md` — **the anti-gaming layer**: verify MEDDPICC against Fathom/email/notes/Slack; verdicts + effect on score.
- `references/run_record.md` — the hygiene-score model + the `Hygiene Run` object mapping + the two-layer architecture (scheduled batch vs rep skill).
- `references/checks.md` · `references/meddpicc_rubric.md` · `references/corrections.md` — the hygiene checks (for on-demand scoring), with the false-positive suppressions.
- `references/reference_data.md` — pipeline/stage IDs, property set, the `Hygiene Run` object `2-63704277`.
- `references/connector_mapping.md` — HubSpot read/write tools + the query grammar.

---
*v1.14 (2026-06-16): **Doc-sync to the engine + Day-1 feedback (manager view).** (1) Documents the LIVE **stage<->close-date coherence flag** (D-40): an early-stage (Discovery/Qualified) open deal closing <=30d out -> CRITICAL, any open deal past its close date -> WARNING (Validate+/open-Won exempt from the imminent-CRITICAL); it joins the **forecast-threat set** (so it now lands in the at-risk columns) and is a scored flag in the per-deal hygiene_score. (2) New **closed-lost integrity** manager view (read-only, never score-affecting): write-off legibility, missing `closed_lost_reason`, same-company **recreate** detection, and **on-hold share** legibility - so a score that rose by writing deals off or padding the book with "on hold" deals is visible (items 1b/2/3/7d). (3) The engine `parse_hold` "may" bug is fixed (D-42) so on-demand scoring no longer reads a bare "may" as a hold. `scorecard.md` + shared `checks.md`/`reference_data.md`/`run_record.md`. See `DECISION_LOG` D-40/D-41/D-42/D-43.*
*v1.13 (2026-06-07): **Company-association labels are batch-handled, not a rep-run action.** The connector can't read
deal→company association typeIds (EC 78 / Reseller 3 / Distributor 80), so the twice-daily batch (`audit_associations.py`)
owns them — auto-tags the obvious End-Customer via REST, flags the ambiguous. Removed the stale "EC/reseller labels are yours"
guidance from the shared references; **Champion/EB contact labels (82/7) stay the rep's**. See `DECISION_LOG` D-36.*
*v1.12 (2026-06-07): **Scoring-doc sync to the batch (two fixes).** (1) Aging multiplier **capped at ×2** (`<7d ×1 · ≥7d ×2`) —
removed the stale `>30d ×3` tier in `run_record.md` (line 28) that contradicted both the batch and this doc's own line 89.
(2) **`blocker uncaptured` is ADVISORY, not scored** — the batch never penalizes an empty `blockers` field (it only reads it
as a hold-until date). `run_record.md` + `checks.md`. See `DECISION_LOG` D-35.*
*v1.11 (2026-06-07): **Scores are deterministic; the resolver is a separate recommend-only pass.** The scorecard, every
rep score, and the dark/stalled/at-risk you review are computed **purely from HubSpot deal fields** — Cleanliness (80) +
Cadence (20), no LLM, no email/transcript/meeting content in the number (validated: the resolver moved 1 of 70 scores).
The engagement resolver runs as its **own daily recommend-only pass** (`resolve_engagements.py` / `CIQ_Hygiene_Resolver`)
and writes `engagement_resolution.json` — true **end customer** (tagged wrong/missing), **duplicate vs distinct-scope**,
**thin-next-step**, and body-verified contact — for you to act on in 1:1s. It does **not** feed the scorecard. Applying
any of it (re-tag EC, consolidate dupes) stays a human decision — no auto CRM write. **Supersedes v1.10's** "feeds the
manager view." See `DECISION_LOG` D-32.*
*v1.10 (2026-06-06): **Engagement resolver feeds the manager view.** For channel deals + dark/stalled forecasted deals,
a server-side LLM resolver reads email bodies + Fathom transcripts and produces a **body-verified `true_last_contact`**
(so the at-risk/dark you see on those deals reflects the real customer-side engagement, not a reseller's cross-deal
activity), plus **review-only recommendations**: true **end customer** (when tagged wrong/missing), **duplicate vs
distinct-scope**, and **thin-next-step**. Surface these in 1:1s; applying them (re-tag EC, consolidate dupes) stays a
human decision — no auto CRM write. See `DECISION_LOG` D-31 + the resolver design spec.*
*v1.9 (2026-06-06): **Anti-gaming + reseller + blocker-hold refinements** (shared `checks.md`/`corrections.md` #36–#37).
Next-step freshness now requires a **material** edit (a comma can't refresh it; same guard gates Cadence "worked"), and the
manager additionally judges next-step **quality** — a "thin next-step" (vague filler vs a real forward-looking action),
verified against call/email content like MEDDPICC. End-customer dark sweep **excludes reseller/distributor/partner**
activity (cross-deal pollution). A customer **hold-until** date in `blockers` suppresses dark/stalled until ~a week out.*
*v1.8 (2026-06-06): **Cadence → coverage-graded** (20 × deals-worked-in-14d ÷ total; via shared `run_record.md` + scorecard explainer). On-demand scoring + leaderboard reflect it.*
*v1.7 (2026-06-06): **Score model → Variant B** (Cleanliness 80 + Cadence 20, no Resolution; recalibrated stall thresholds;
aging cap ×2) via shared `run_record.md` + the scorecard explainer. On-demand scoring + the leaderboard reflect the new model.*
*v1.6 (2026-06-06): Inherits the **Next-Step staleness fix** via shared references (`checks.md`/`corrections.md` #34) —
staleness now uses the field's last-edit timestamp, not a scraped text date; on-demand scoring reflects the corrected model.*
*v1.5 (2026-06-05): **MEDDPICC evidence verification** added (`references/meddpicc_verification.md`) — the manager skill now
cross-checks each populated MEDDPICC claim against Fathom calls, email bodies, notes, and public Slack, crediting only
evidenced qualification and flagging unsupported (gamed) / contradicted fields (closes the gap that content-marker scoring
alone can't catch). Manager skill **no longer writes the `Hygiene Run` object** — the twice-daily server-side batch is the
authoritative writer (reps/managers can't write the custom object via the connector); on-demand runs are fresh in-chat
snapshots. Added a **scoring explainer** (how a rep reaches 100) and a **partner/channel-deal caveat** (DD-11).*
*v1.4 (2026-06-05): Graceful when the connector can't enumerate the `Hygiene Run` custom object (common in browser) — point
to the HubSpot native list view for the stored board + use on-demand scoring; never fail or fabricate.*
*v1.3 (2026-06-05): Excludes non-rep / test owners (Matthew Hayden, RevOps) from the scorecard; quarter-end derives from the CIQ fiscal quarter.*
*v1.2 (2026-06-05): Risk buckets refined — **Committed** = COMMIT forecast category, plus **This-Qtr** / **Overdue** / **Pipeline** timing (forecasted deals only; OMIT/CLOSED excluded); scorecard leads with Committed + This-Qtr at-risk.*
*v1.1 (2026-06-05): Two-number scorecard — leads with **Committed-at-risk $** (this-quarter forecast on unhealthy deals)
alongside the Hygiene score; reads the new `committed/pipeline/total_at_risk_usd` + `risk_pct` + `meddpicc_thin` fields; MEDDPICC content-marker scored.*
*v1 (2026-06-05): Manager/leadership scorecard skill. Reads `Hygiene Run` (`2-63704277`) for the per-rep leaderboard +
trend + cadence + aging; scores any rep / the team on demand (writing records); drills into a rep. Read-only on reps'
deals; same score model + object as the rep skill.*
