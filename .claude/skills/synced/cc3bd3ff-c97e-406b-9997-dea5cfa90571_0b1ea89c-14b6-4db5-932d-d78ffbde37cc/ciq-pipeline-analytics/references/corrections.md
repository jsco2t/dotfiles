# Corrections Catalog — traps that have produced wrong numbers (read before your first query)

Each entry: what goes wrong → the rule. These are real, documented failures, not hypotheticals. Entries here override anything that conflicts elsewhere.

### PA-1 | "Open" via `hs_is_closed = false` includes WON deals
The Sales **Won** stage (`93217107`, won-awaiting-finance-booking) reports `hs_is_closed = false`. Filtering on it pulled a booked deal into an "open" set, where its past close date was then "fixed" — re-dating a Won deal in error (2026-07-07 incident). **Rule:** OPEN = the explicit stage whitelist (reference §3). Always.

### PA-2 | Raw `amount` inflates KRW ~1430×
`amount` is native deal currency. A ₩700M deal is ≈ $490K, not $700M. **Rule:** `net_new_arr` (USD) → `amount_in_home_currency`. Never raw `amount`.

### PA-3 | Hardcoded stage probabilities have diverged across docs
Two "verified" probability sets disagree at the middle stages (Qualified 15 vs 20, Validate 24 vs 40, Propose 51 vs 60, In Procurement 83 vs 80). **Rule:** pull `hs_deal_stage_probability` live; the reference table is a fallback/sanity set; note any divergence. Renewal stages ≫ Sales stages at the same name.

### PA-4 | `hs_projected_amount` is NOT the weighted pipeline
HubSpot's native weighted field multiplies **raw `amount`** by probability — wrong basis (PA-2) and wrong value semantics. **Rule:** weighted = `net_new_arr × hs_deal_stage_probability`, computed by you.

### PA-5 | Counting Won deals in open/weighted pipeline double-counts
A won deal's ARR is already inside company `active_arr`. **Rule:** WON set is excluded from open pipeline, weighted pipeline, and forward projections.

### PA-6 | Company ARR ≠ Σ deal ARR
Summing deal `hs_arr` per company stacks renewed/expanded contracts and disagrees with the books. **Rule:** current ARR = company `active_arr` (RevOps-curated), filtered `> 0`.

### PA-7 | Closed Lost zeroes `net_new_arr`
Loss reporting off `net_new_arr` shows $0 losses. **Rule:** loss values via `amount_in_home_currency`.

### PA-8 | Raw stage IDs in output
`93217105` means nothing to a human, and mislabeled stages have caused misread reports. **Rule:** always render stage names; unknown ID → say "UNKNOWN STAGE <id>" loudly, don't guess.

### PA-9 | The Alt/Revenue pipeline is internal
Including `793851464` inflates every number. **Rule:** exclude it from all queries, always.

### PA-10 | The 10k search cap silently truncates sums
An unscoped cross-company sum stops at 10,000 records and reports a plausible-looking wrong total. **Rule:** scope filters (`active_arr > 0`, date windows, pipeline) so the result set is bounded; state N in the method note.

### PA-11 | January is Q4
FY26 runs Feb 2026 – Jan 2027. Putting January in Q1 shifts quarter totals. **Rule:** fiscal mapping in reference §1.

### PA-12 | Vendor and internal activity are not pipeline signals
Allytics (CIQ's demand-gen vendor) and @ciq.com activity are test/internal data. Hardcoded owner-name maps have fabricated rep names in production reports. **Rule:** exclude vendor/internal domains; resolve owners live.
