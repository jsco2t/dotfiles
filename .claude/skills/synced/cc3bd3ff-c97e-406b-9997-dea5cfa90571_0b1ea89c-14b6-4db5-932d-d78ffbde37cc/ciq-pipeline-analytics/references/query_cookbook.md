# Query Cookbook — connector patterns for each metric

## Step 0 — detect your tools, then branch (do not hunt or stall)
Rep connectors vary. Check which HubSpot tools are present:
- **Only `query_crm_data` (SQL)** → the common rep case. Everything below has a SQL form. **Call the connector's Tool Guidance first** (required; it carries exact syntax). If you hit `Missing required scope: reporting-base-read`, the user must enable "Query portal data" — there is no other read path; never fabricate.
- **Richer read set** (`search_crm_objects`, `get_crm_objects`, `get_properties`, `search_owners`) → prefer object search for stage-set filters and the owners tool for name resolution.
- **`manage_crm_objects` present?** Irrelevant — this skill never writes (SKILL golden rule 1).

**SQL surface constraints:** one object type per query · AND-only (no OR/LIKE/JOIN/CASE/DISTINCT) · dates as `BETWEEN 'YYYY-MM-DD'` · cross-object via `OBJECT.property` (≤2 associated types) · `GROUP BY` + `COUNT(*)`/`SUM()`/`DATE_TRUNC` supported · no HAVING.
**Object-search constraints:** date filters in Unix **milliseconds** · 10,000-record cap (scope your filters) · `IN` operator takes a `values` array.

**The stage-set trick for SQL (AND-only, no NOT IN):** query per pipeline **grouped by `dealstage`**, then apply the OPEN/WON/LOST sets from `reference_data.md` §3 to the grouped rows yourself. Never filter on `hs_is_closed`.

---

## R1 — Open pipeline by stage (feeds M1, M8)
SQL (per pipeline; run once for `45314112`, once for `49231982`):
```sql
SELECT dealstage, COUNT(*), SUM(net_new_arr)
FROM DEAL
WHERE pipeline = '45314112'
GROUP BY dealstage
```
Keep only OPEN-set rows; render stage names. Object-search form: filter `pipeline EQ` + `dealstage IN [<open-stage ids>]`.

## R2 — Weighted pipeline (M2)
Pull OPEN deals with `net_new_arr`, `hs_deal_stage_probability`, `dealstage`, `pipeline`, `closedate`; compute Σ (net_new_arr × probability) yourself. Quarter scope: add `closedate BETWEEN '<q-start>' AND '<q-end>'`. If `hs_deal_stage_probability` is unavailable, use the fallback table and say so in the method note.

## R3 — Booked FYTD / quarter (M3)
```sql
SELECT dealstage, SUM(net_new_arr), COUNT(*)
FROM DEAL
WHERE pipeline = '45314112' AND closedate BETWEEN '2026-02-01' AND '<today>'
GROUP BY dealstage
```
(and again for the Renewal pipeline). Keep only WON-set rows.

## R4 — Current ARR + Net New YTD (M4, M5, M6)
```sql
SELECT SUM(active_arr), COUNT(*) FROM COMPANY WHERE active_arr > 0
SELECT SUM(fy25_arr), COUNT(*) FROM COMPANY WHERE fy25_arr > 0
```
The `> 0` filters are mandatory (curated scope + the 10k cap). Ladder math per M6.

## R5 — Rep rollup (M9)
Add `hubspot_owner_id` to R1/R2/R3 selections; `GROUP BY hubspot_owner_id` works for counts/sums. Resolve IDs → names via `search_owners` (richer connector) or ask for the rep's id / use Tool Guidance's current-user resolution (thin connector). Never guess a name.

## R6 — Product mix (M10, M11)
```sql
SELECT DEAL.hs_object_id, product_group, product_category, hs_arr
FROM LINE_ITEM
WHERE DEAL.pipeline = '45314112'
```
Join to the R1/R2 deal pull yourself and allocate proportionally by line-item `hs_arr`.

## R7 — Forecast rollup (M12)
```sql
SELECT hs_manual_forecast_category, COUNT(*), SUM(net_new_arr)
FROM DEAL
WHERE pipeline = '45314112'
GROUP BY hs_manual_forecast_category
```
Post-filter to OPEN deals via a second grouped-by-stage pull, or select `dealstage` too and cross-tabulate.

## R8 — Past-due / forecast bloat / renewal risk (M13)
Past-due: OPEN-set deals with `closedate BETWEEN '2024-01-01' AND '<yesterday>'`. Select `hs_manual_forecast_category`, `net_new_arr`, `dealstage` to compute the bloat cut. Renewal risk: Renewal-pipeline OPEN deals selecting `term_end`, `net_new_arr`, `renewal_outlook`.

## R9 — Win rate / created-vs-closed (M14)
Won/lost per window via R3 pattern (keep WON rows / LOST rows; lost dollars via `SUM(amount_in_home_currency)` on LOST-set rows). Created: `WHERE createdate BETWEEN …`.

---

## Presentation checklist (every answer)
- Stage/pipeline NAMES, owner NAMES (live-resolved) — no raw IDs.
- USD figures; flag any KRW/JPY artifact you had to normalize.
- The method note: basis · filters · probability source · N deals · as-of time.
- Fiscal quarters per the CIQ calendar (Jan = Q4).
- If a pull hit a cap, was scoped, or dropped records (no-company deals, missing properties) — say what was dropped; silent truncation reads as "covered everything."
