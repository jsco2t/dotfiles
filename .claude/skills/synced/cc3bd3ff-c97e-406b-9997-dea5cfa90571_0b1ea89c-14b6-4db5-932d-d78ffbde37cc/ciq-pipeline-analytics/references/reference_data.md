# Reference Data — CIQ Pipeline Analytics

**Portal:** 22461953 · **Fiscal year:** FY26 = Feb 1 2026 – Jan 31 2027 · **Last verified against live portal:** 2026-07-08

## 1. Fiscal calendar
Q1 Feb–Apr · Q2 May–Jul · Q3 Aug–Oct · Q4 Nov–Jan. **January = Q4.**
Month→quarter: 2,3,4→Q1 · 5,6,7→Q2 · 8,9,10→Q3 · 11,12,1→Q4.
Booking month = `closedate`. A Closed Won deal counts as booked even before `term_start`.

## 2. Pipelines
| Pipeline | ID | In scope? |
|---|---|---|
| Sales | `45314112` (a.k.a. `default`) | YES |
| Renewal | `49231982` | YES |
| Alt/Revenue | `793851464` | **NO — exclude from ALL reporting, always** |

## 3. Stages — names, probability fallback, and the three stage sets
**Probabilities: pull `hs_deal_stage_probability` live per deal.** The columns below are the FY26 fallback/sanity set — if live differs, live wins; note the divergence.

**Sales pipeline (`45314112`)**
| Stage | ID | Fallback prob | Set |
|---|---|---|---|
| Discovery | `93217102` | 10% | OPEN |
| Qualified | `93217103` | 20% | OPEN |
| Validate | `93217104` | 40% | OPEN |
| Propose & Negotiations | `93217105` | 60% | OPEN |
| In Procurement | `93217106` | 80% | OPEN |
| Pending Approval | `1205882270` | 90% | OPEN |
| Won | `93217107` | 98% | **WON — ⚠ reports `hs_is_closed=false`** |
| Closed Won | `143973802` | 100% | WON |
| Closed Lost | `93217108` | 0% | LOST |

**Renewal pipeline (`49231982`)** — same-named stages carry HIGHER probabilities here (renewals are more predictable); never apply the Sales table to a Renewal deal.
| Stage | ID | Fallback prob | Set |
|---|---|---|---|
| Upcoming Renewals | `125777759` | 90% | OPEN |
| Outreach Required | `125777760` | 95% | OPEN |
| Renewal Initiated | `125777761` | 96% | OPEN |
| Propose & Negotiations | `125777762` | 97% | OPEN |
| In Procurement | `1048488587` | 98% | OPEN |
| Pending Approval | `1224166053` | 98% | OPEN |
| Won | `125777763` | 100% | WON |
| Closed Won | `125777764` | 100% | WON |
| Closed Lost | `125777765` | 0% | LOST |

**The three sets (use these everywhere):**
- **OPEN** = the whitelisted open stages above. This is the ONLY correct definition of "open deal." Never use `hs_is_closed = false` — it includes Sales Won `93217107`.
- **WON** = Won + Closed Won (both pipelines). Used for bookings. Excluded from open/weighted pipeline (their ARR already lives in company `active_arr` — including them double-counts).
- **LOST** = Closed Lost. `net_new_arr` is auto-zeroed here; use `amount_in_home_currency` for loss values.

Stage-name casing from the API can vary ("Pending approval") — normalize for display. Never display a raw ID.

## 4. Deal properties (the analytics set)
| Property | Use |
|---|---|
| `dealname`, `dealstage`, `pipeline`, `dealtype` | identity; normalize dealtype casing (newbusiness→"New Business") |
| `hubspot_owner_id` | resolve to a name LIVE (owners tool); never from memory |
| `closedate` | forecast date (open) / booked date (won) — drives quarter attribution |
| `net_new_arr` | **THE canonical deal value (USD).** Zeroed on Closed Lost; can be negative on downsized renewals (= churn signal) |
| `amount_in_home_currency` | USD fallback: loss values, pre-FY26 won deals |
| `amount` | ⛔ never use — native deal currency (KRW deals ~1430× inflated) |
| `hs_projected_amount` | ⛔ never use — HubSpot native weighted, computed off raw `amount` |
| `hs_arr` / `hs_tcv` / `hs_acv` | full-contract ARR / TCV / ACV — context only, never summed for pipeline or company ARR |
| `hs_deal_stage_probability` | live per-deal probability for weighted pipeline |
| `hs_manual_forecast_category` | forecast rollup — values: `OMIT` (Not forecasted) · `BEST_CASE` (Upside) · `Renewal` · `COMMIT` (Committed) · `CLOSED` (Closed won) · `At Risk` |
| `renewal_outlook` | renewal-health weighting %: Confident=95 · On Track=85 · At Risk=40 · Critical=10 · Renewed=100 · Churned/Non-renewable=0 |
| `term_start` / `term_end` | contract term; contract status is DERIVED at query time (active = start ≤ today ≤ end) |
| `deal_currency_code` | USD / EUR / KRW / JPY |

## 5. Company properties
| Property | Use |
|---|---|
| `active_arr` | **Authoritative current ARR (USD), RevOps-curated.** Always filter `> 0` when summing (also avoids the 10k search cap silently truncating) |
| `fy25_arr` | FY26 opening ARR base: Net New YTD = Σ active_arr − Σ fy25_arr |
| `previous_month_arr` | "previous ARR" (NOT `company_original_arr`, which is the first-ever deal) |
| `csm`, `hubspot_owner_id`, `domain`, `name` | rollups and vendor filtering |

## 6. Line-item properties (product mix)
`name`, `hs_sku`, `hs_arr`, `price`, `quantity`, `class`, `product_category`, `product_group`.
Product allocation of a deal: `product_net_new = deal.net_new_arr × (line_item.hs_arr ÷ Σ line_item.hs_arr)`.

## 7. FY26 goals
| Metric | Value |
|---|---|
| FY26 ARR goal | **$20,000,000** |
| FY26 opening ARR | Σ company `fy25_arr` (≈ $8.72M) |
| Monthly target | (goal − current ARR) ÷ 12 |

## 8. Currency
USD reporting via `net_new_arr` (already USD) or `amount_in_home_currency`. Manual conversion fallback: KRW ÷ 1430 · JPY ÷ 151 · EUR × 1.05. KRW deals (KT Corp, Samsung, LG entities, Softbank, NTT, Toyota Systems…) carry `amount`/`hs_arr` in KRW — a giant native number is a currency artifact, not a giant deal.

## 9. Standing exclusions
- Alt/Revenue pipeline `793851464` — always.
- Vendor/test/internal domains: Allytics (CIQ demand-gen vendor), @ciq.com activity, consumer-ISP/bot domains — never prospects.
- PROSERV is excluded from comp-facing net-new ARR; note it when a comp-adjacent number is requested (then route comp itself to RevOps).

## 10. Platform quirks that corrupt numbers
- Object-search caps at **10,000 records** — unscoped sums silently truncate. Scope filters (`active_arr > 0`, date ranges, pipeline).
- Date filters in object-search: **Unix milliseconds**, not ISO. (SQL surface uses `'YYYY-MM-DD'` strings — see cookbook.)
- Deal-embedded company fields are stale; live-pull the company record.
- Some deals have no associated company — fall back to the first segment of `dealname` before " - " for display.
