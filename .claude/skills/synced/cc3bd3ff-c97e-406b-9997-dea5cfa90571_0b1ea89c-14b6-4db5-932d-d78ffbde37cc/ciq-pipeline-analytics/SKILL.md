---
name: ciq-pipeline-analytics
description: Use when a CIQ rep, manager, or exec asks for pipeline numbers or revenue analysis — "what's my pipeline", "weighted pipeline this quarter", "how much have we booked", "stage distribution", "pipeline by rep / by product", "coverage", "path to $20M", "forecast rollup", "at-risk / past-due deals", "renewal risk", "net new ARR", "current ARR", "win rate". Read-only reporting through the HubSpot connector. FY26 (Feb–Jan), portal 22461953, Sales + Renewal pipelines only.
---

# CIQ Pipeline Analytics — read-only reporting (v1.0)

Answer pipeline and revenue questions **consistently**: the same question must produce the same number no matter who asks or when. Every metric has ONE definition (in `references/metric_definitions.md`) and every answer states its basis. This skill **never writes to HubSpot** — it is the reporting lens, not a fix-it tool.

**Core loop:** map the question to a defined metric → run the cookbook query (`references/query_cookbook.md`) → compute per the definition → present with a method note (basis property, filter set, as-of time, deal count). If the question doesn't match a defined metric, say so, agree the definition with the user explicitly, present it clearly labeled as ad-hoc, and suggest RevOps codify it — never silently invent a formula.

## What you need connected
- **HubSpot** (required) — a read-only connector is fully sufficient; this skill only reads. Some rep connectors expose only `query_crm_data` (SQL): that works — see the cookbook's Step 0.

## Golden rules (follow exactly)

1. **⛔ READ-ONLY — this skill NEVER writes to HubSpot (hard rule).** No property updates, no associations, no "quick fixes," no exceptions. Do not call `manage_crm_objects` for any reason. When analysis surfaces something to fix, name it and **route it**: data cleanup → `/ciq-deal-hygiene` (reads the daily Drive report); new deal → `ciq-deal-creation`; closing/won → `deal-closing-workflow`; anything else → RevOps. Closing/losing/winning and close-date edits are NEVER yours — a Won/closed deal's `closedate` is the booked date and is untouchable.

   | Temptation | Reality |
   |---|---|
   | "It's a small fix while we're already looking at the deal" | An ad-hoc "fix" from an analytics-style chat is exactly how a Won deal's booked close date got re-dated in error. Route it. |
   | "The rep explicitly asked me to update it" | Still no. The write-capable skills carry the safety gates (fresh-read, Won-stage drop, append-only). This one has none — by design. |
   | "It's obviously wrong data, fixing it improves the report" | Report the discrepancy WITH evidence. RevOps or the hygiene flow fixes it with an audit trail. |

   **Red flags — STOP if you are about to:** call a write tool · draft a property value "to apply" · reason about which stage/date a deal *should* have. All of these mean: report, don't touch.

2. **Principle 0 — every number shows its basis.** Under every reported figure, state: value basis (e.g. `net_new_arr`), filter set (pipelines, stages, date range), probability source, deal count, and as-of timestamp. A number with no basis is a guess; don't present it.

3. **"Open" = the open-stage whitelist — NEVER `hs_is_closed = false`.** HubSpot reports `hs_is_closed = false` on the Sales **Won** stage (a won deal awaiting finance booking), so that filter silently includes won deals — this exact trap caused a booked deal to be re-dated. Always filter `dealstage` IN the explicit open-stage lists in `references/reference_data.md` §3.

4. **Deal value = `net_new_arr`.** The canonical USD pipeline value. Fallback for loss values (Closed Lost zeroes `net_new_arr`): `amount_in_home_currency`. **Never raw `amount`** (deal-currency — inflates KRW deals ~1430×). **Never `hs_projected_amount`** (HubSpot's native weighted field — computed off raw `amount`). `hs_arr` is full-contract ARR for context only; never sum it for pipeline or company ARR.

5. **Current ARR = Σ company `active_arr`** (filtered `active_arr > 0`) — the RevOps-curated source of truth. Never derive current ARR by summing deals. Net New YTD = Σ `active_arr` − Σ `fy25_arr`.

6. **Probabilities are pulled live** (`hs_deal_stage_probability` per deal). The FY26 table in `reference_data.md` §3 is a fallback/sanity set only — if live differs, live wins and you note the divergence. Renewal-pipeline stages carry much higher probabilities than same-named Sales stages: never mix the tables.

7. **Never output a raw stage or pipeline ID.** Render names via the tables in `reference_data.md`. Same for owners: resolve `hubspot_owner_id` → name live via the owners tool; never from memory (hardcoded maps have produced fabricated names).

8. **CIQ fiscal calendar:** FY26 = Feb 2026 – Jan 2027. Q1 Feb–Apr · Q2 May–Jul · Q3 Aug–Oct · Q4 Nov–Jan. **January belongs to Q4.** Booking month = `closedate` (never `term_start`).

9. **Standing exclusions:** the Alt/Revenue pipeline is excluded from ALL reporting; vendor/test domains (e.g. CIQ's demand-gen vendor Allytics) and @ciq.com activity never count as prospects; PROSERV is excluded from comp-facing net-new (note when relevant).

10. **Know the platform limits before summing:** the search surface caps at 10,000 records (use `> 0`/scoped filters so sums don't silently truncate); cross-company sums must filter `active_arr > 0`; date filters in object-search calls use Unix **milliseconds**.

## What this skill does NOT do
- **No writes of any kind** (golden rule 1) — including "harmless" stamps or corrections.
- **No hygiene scoring or flag re-derivation** — the daily RevOps report/scorecard is authoritative; questions about scores → `/ciq-deal-hygiene` (reps) or `ciq-hygiene-manager` (managers).
- **No commission/comp math** — comp runs in the RevOps engine with its own credit rules; don't approximate it.
- **No ARR-snapshot creation or reconciliation** — the snapshot batch owns that.
- **No slippage/close-date-movement analysis** — that needs property history, which the connector cannot read; tell the user it's a RevOps request, don't approximate from current values.
- **Authoritative product-level ARR** — the quick product split (metric M11) is an approximation; the RevOps in-term contract de-stack is the source of truth for official numbers.

## Reference files (consult as needed)
- `references/reference_data.md` — portal, fiscal calendar, pipeline & stage tables (with probability fallback + open/won/closed sets), property glossary, currency, forecast categories, exclusions.
- `references/metric_definitions.md` — the ONE definition of each metric (M1–M14): formula, basis, filters, presentation, pitfalls.
- `references/query_cookbook.md` — connector detection (Step 0) and copy-adapt query recipes for every metric, SQL + object-search forms.
- `references/corrections.md` — the trap catalog (PA-1…PA-12): read before your first query in a session.

---
*Changelog — v1.0 (2026-07-08): Initial skill. Replaces the retired "Pipeline Analytics v2" project doc. Definitions sourced from the RevOps FY26 pipeline reporting reference and the CIQ golden-rules canon; forecast-category and property facts verified live against portal 22461953 on 2026-07-08. Built read-only by design following the 2026-07-07 connector write incident on a Won deal.*
