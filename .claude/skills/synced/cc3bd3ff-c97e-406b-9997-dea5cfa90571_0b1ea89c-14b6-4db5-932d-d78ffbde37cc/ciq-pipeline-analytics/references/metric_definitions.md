# Metric Definitions — the ONE way each number is computed

Every metric this skill reports is defined here. If a question doesn't map to one of these, agree an explicit ad-hoc definition with the user, label it ad-hoc, and suggest RevOps codify it. Stage sets (OPEN/WON/LOST) and property meanings are in `reference_data.md`.

**Every reported number carries a method note:** basis property · filter set (pipelines, stage set, date range) · probability source · deal count · as-of timestamp.

---

## M1 — Open Pipeline
Σ `net_new_arr` over deals in the **OPEN** stage set, pipelines Sales + Renewal.
- Optional scopes: owner, fiscal quarter (`closedate` window), product (via line items).
- Pitfalls: never `hs_is_closed=false` (PA-1); negative renewal `net_new_arr` stays in (it is real downsell risk — call it out separately).

## M2 — Weighted Pipeline
Σ (`net_new_arr` × probability) over **OPEN** deals.
- Probability = live `hs_deal_stage_probability` per deal; fallback table only if live is unavailable (say so).
- WON deals are excluded — their ARR is already inside company `active_arr`; including them double-counts (PA-5).
- Never `hs_projected_amount` (PA-4).

## M3 — Booked (FY26 / quarter / month)
Σ `net_new_arr` over deals in the **WON** set with `closedate` in the window.
- Booking month = `closedate`, never `term_start`.
- Pre-FY26 won deals valued via `amount_in_home_currency` when `net_new_arr` is absent.
- Renewal-won uplifts hit the WON close month even when the new term starts later.

## M4 — Current ARR
Σ company `active_arr` filtered `active_arr > 0`.
- The company record is authoritative (RevOps-curated). NEVER sum deal `hs_arr` (PA-6).

## M5 — Net New YTD
Σ `active_arr` − Σ `fy25_arr` (same `> 0`-scoped company pull). Churn is already netted.

## M6 — Path to $20M (the ladder — lead exec summaries with this)
1. FY26 opening ARR = Σ `fy25_arr` (≈ $8.72M)
2. \+ Net New YTD (M5)
3. = Current ARR (M4)
4. Remaining to goal = $20,000,000 − Current ARR

## M7 — Monthly Target & Coverage
Monthly target = (20,000,000 − M4) ÷ 12.
Coverage = M2 (weighted open) ÷ monthly target. State the window the weighted sum covers.

## M8 — Stage Distribution
Per OPEN stage: deal count, Σ `net_new_arr`, Σ weighted. Group by pipeline; render stage NAMES.

## M9 — Rep Rollup
Per owner (resolved live): M1, M2, M3-FYTD, quarter breakdown by `closedate`, deal-type mix.
Owner = deal `hubspot_owner_id` (company owner may differ; say which you used).

## M10 — Product Mix (pipeline)
Allocate each OPEN deal's `net_new_arr` across its line items proportionally by line-item `hs_arr`; sum by `product_group` (or `product_category`). Renewals with `net_new_arr` = 0 correctly contribute $0.

## M11 — ARR by Product (approximation — label it)
From WON deals whose term is currently active (`term_start ≤ today ≤ term_end`), allocate `hs_arr` across line items and sum by product. **Label as approximate**: authoritative product-level ARR is the RevOps in-term contract de-stack; totals must reconcile to M4, not exceed it.

## M12 — Forecast Rollup
Group OPEN deals by `hs_manual_forecast_category` (values in reference §4): Σ `net_new_arr` + count per bucket. "Forecasted" = `COMMIT` + `BEST_CASE`.

## M13 — Forecast Bloat / Past-Due (the honesty check)
- **Past-due:** OPEN deals with `closedate` < today. Escalate by stage: early-stage past-due = stale forecast date; In Procurement/Pending Approval past-due = urgent.
- **Forecast bloat:** Σ `net_new_arr` on `COMMIT`/`BEST_CASE` deals that are past-due (this skill's computable proxy). Deep at-risk analysis (dark/stalled/thin-MEDDPICC on forecasted deals) belongs to the hygiene manager skill — route, don't re-derive.
- **Renewal risk:** Renewal-pipeline OPEN deals in early stages + `term_end` proximity + negative `net_new_arr` + low `renewal_outlook` (≤40 = At Risk/Critical).
- ⚠ Past-due on an OPEN deal means "the forecast date was missed" — it NEVER means "close it lost," and this skill never touches the deal either way.

## M14 — Win Rate & Created-vs-Closed
- Win rate (window, by `closedate`): WON count ÷ (WON + LOST count). Dollar-basis variant: Σ won `net_new_arr` ÷ (Σ won `net_new_arr` + Σ lost `amount_in_home_currency`) — say which basis you used.
- Created vs Closed (window): deals with `createdate` in window vs deals leaving via WON/LOST in window — pipeline in/outflow.

## Explicitly NOT computable here
- **Slippage (close-date movement)** — needs property history; connector can't read it. Route to RevOps.
- **Hygiene scores/flags** — the daily batch + Drive report are authoritative.
- **Commission/attainment** — the comp engine owns credit rules (owner/co-owner/CSM splits, PROSERV & vendor exclusions).
