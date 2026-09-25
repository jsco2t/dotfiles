# CIQ Reference Data (for deal creation)

**Portal:** 22461953 · **Fiscal year:** Feb 1 – Jan 31 · **Last reviewed:** 2026-07-08

> This is the shared-facts file. Where it conflicts with `corrections_log.md`, the corrections log wins. **Two rules override anything written here as a static value:** (1) resolve owner names **live** from the HubSpot owners object — never trust a hardcoded name; (2) for any forecasting, pull `hs_deal_stage_probability` **live** — the probability values below are known to diverge across systems and are NOT used by deal creation.

## Contents
1. Fiscal calendar
2. Pipelines
3. Sales pipeline stages
4. Renewal pipeline stages
5. Stage probabilities (⚠️ conflict — do not hardcode)
6. Deal types & routing
7. Currencies
8. Close-date semantics
9. Owner resolution (dynamic-first) + known-gotcha table
10. Associations (labels via the connector) + type IDs
11. MEDDPICC contact-field status
12. Competition enum
13. Product classes & categories
14. Deal source & channel flag

---

## 1. Fiscal calendar
FY26 = Feb 1 2026 – Jan 31 2027. Q1 Feb–Apr · Q2 May–Jul · Q3 Aug–Oct · Q4 Nov–Jan (Jan is Q4).

## 2. Pipelines
| Pipeline | ID | Use |
|---|---|---|
| Sales | `45314112` (a.k.a. `default`) | New Business + Expansion — **default for creation** |
| Renewal | `49231982` | Renewals |
| Alt/Revenue | `793851464` | **EXCLUDE from all reporting, always.** Not used for creation. |

## 3. Sales pipeline stages (`45314112`)
Creation entry point is **Discovery**.
| Stage | ID |
|---|---|
| Discovery | `93217102` ← creation default |
| Qualified | `93217103` |
| Validate | `93217104` |
| Propose & Negotiations | `93217105` |
| In Procurement | `93217106` |
| Pending Approval | `1205882270` |
| Won | `93217107` |
| Closed Won | `143973802` |
| Closed Lost | `93217108` |

> ⚠️ **`hs_is_closed = false` does NOT mean "open."** HubSpot reports `hs_is_closed = false` on the **Won** stage (`93217107`) — a won deal awaiting finance booking, *before* the terminal Closed Won (`143973802`). To find open deals, **exclude the Won + closed stage IDs explicitly** (`93217107` / `143973802` / `93217108`); don't filter on `hs_is_closed` alone. And **never edit `closedate` on a Won or closed deal** (see §8). This is the trap behind the Rakuten Bridge Expansion re-date and hygiene incident #38.

## 4. Renewal pipeline stages (`49231982`)
Creation entry point is **Upcoming Renewals**. **Stage names were changed** — the old "90/60/30 days to Renewal" labels are wrong; use these:
| Stage | ID |
|---|---|
| Upcoming Renewals | `125777759` ← renewal creation default |
| Outreach Required | `125777760` (was "90 days to Renewal") |
| Renewal Initiated | `125777761` (was "60 days to Renewal") |
| Propose & Negotiations | `125777762` (was "30 days to Renewal") |
| In Procurement | `1048488587` |
| Pending Approval | `1224166053` |
| Won | `125777763` |
| Closed Won | `125777764` |
| Closed Lost | `125777765` |

## 5. Stage probabilities — ⚠️ CONFLICT, do not hardcode
Two "verified" probability sets exist and disagree at the middle stages. Deal **creation does not use probabilities** (new deals enter at Discovery), so this section is informational — but any analytics/forecasting must **pull `hs_deal_stage_probability` live per stage** rather than use either table (pipeline questions belong to `ciq-pipeline-analytics`). See corrections log entry on this.
| Stage | "Feb 8 2026" set (Addendum C / hygiene / pipeline docs) | "Mar 2026 / preferences" set |
|---|---|---|
| Discovery | 10% | 10% |
| Qualified | 15% | **20%** |
| Validate | 24% | **40%** |
| Propose & Negotiations | 51% | **60%** |
| In Procurement | 83% | **80%** |
| Pending Approval | 90% | 90% |
Renewal-pipeline shared stages carry **higher** probabilities than Sales — another reason to read live and check which pipeline a deal is in.

## 6. Deal types & routing
| Value | Label | Pipeline | Default stage |
|---|---|---|---|
| `newbusiness` | New Business | Sales `45314112` | Discovery `93217102` |
| `Expansion` | Expansion | Sales `45314112` | Discovery `93217102` |
| `existingbusiness` | Renewal | Renewal `49231982` | Upcoming Renewals `125777759` |
| `Overages` | Overages | ask rep which pipeline | — |
"Retraction" does **not** exist as a deal type. For `Expansion`, ask whether it's combined with a renewal and set `renewal__expansion` true/false.

## 7. Currencies
`deal_currency_code` ∈ {USD, EUR, KRW, JPY}. Product prices live in currency-specific fields: `hs_price_usd`, `hs_price_eur`, `hs_price_krw`, `hs_price_jpy` (the generic `price` field on products is hidden/legacy — do not use it). Line item unit `price` inherits from the product's currency price when the line item is product-linked.
- `amount` = native currency. `amount_in_home_currency` = USD-normalized (use for USD reporting).
- Manual conversion (quarterly-reviewed): KRW ÷ 1430 · JPY ÷ 151 · EUR × 1.05. A missing `hs_price_{currency}` on the product for the deal's currency is a **hard block** on the line item — get RevOps to configure it.

## 8. Close-date semantics
- On an **open** deal, `closedate` is the rep's **forecasted** close date. A past `closedate` on an open deal = the forecast date was missed → "close date needs updating," **never** "overdue / at risk."
- On a **Won or closed** deal, `closedate` is the **actual booked/won date** — it is naturally in the past and **must never be edited**. Do not treat its past close date as a hygiene problem. (On creation you set a forward-looking `closedate`; you never touch the close date of an existing Won/closed deal.)
- **Defining "open" (do not use `hs_is_closed` alone):** exclude the Won + closed stage IDs explicitly — Sales `93217107`/`143973802`/`93217108`, Renewal `125777763`/`125777764`/`125777765` — because HubSpot reports `hs_is_closed = false` on the Sales Won stage. Relying on `hs_is_closed = false` pulls Won-stage deals in as "open," which is what led to the Rakuten Bridge Expansion close date being re-dated in error.

## 9. Owner resolution — dynamic-first
**Always resolve `hubspot_owner_id` → name from the live HubSpot owners object** (`search_owners`). Hardcoded name maps have produced fabricated names in production reports (e.g. Tom Collins→"Tom Shingler", Chris Repasy→"Chris Ritsos"). The authoritative crosswalk is generated from the owners API — regenerate it, don't retype it. **New deals default to the creating rep as owner**; creating on someone's behalf requires the rep to name the owner explicitly.

**Known-gotcha table — a verification layer only, NOT a source of truth.** If live data ever conflicts with this table, **live data wins and you flag the discrepancy**. This table exists so the errors below don't get re-introduced:
| Owner ID | Correct person | Gotcha |
|---|---|---|
| `329050336` | **David Horn** | 🚨 **NEVER map to James Fitch or any other name.** A prior doc had this as James Fitch — wrong. |
| `82821662` | **Suzanne Spencer-Purcell** | A prior doc had this as "Dave Horn" — wrong. |
| `251398025` | **Rose Stein** | Displays as "Rose Samaniego" in HubSpot — always use **Rose Stein**. |
| `83260009` | James Fitch | Distinct from David Horn's ID above — do not swap. |
| `85100956` | Ramesh Srinivasan | VP Sales. |
| `529285553` | Bjorn Hovland | President (Revenue Leadership). |
| `505633342` | Wesley McGrew | |
| `81176068` | Ally Cho / Tommy Yi | Korea team, **shared** ID — differentiate by deal context. |
| `432367417` | Jimmy Conner | Ascender SE — auto-assigned (see deal_setup file + corrections D-10). |
| `76138901` | Tabatha Wilmot | RevOps / Deal Desk. |
| `80484415` | Derek Nolde | **DEACTIVATED** — do not assign. A prior doc listed this as active "Scott Nolde." |
| `80315854` | Eli Covell | **DEACTIVATED** — do not assign. |
(For a rep not listed, resolve live — do not guess.)

## 10. Associations — labels via the connector (+ type IDs as reference)
**The current native HubSpot connector applies association labels by NAME**, on the `associations` array of a `manage_crm_objects` create or update. Omitting `labels` creates the default (unlabeled) association; specifying `labels` ADDS those labels. Labels must already exist for the object-type pair (all labels below do). The connector cannot READ labels back — confirm in the HubSpot UI during the one-time validation run (corrections D-11).

Pattern (associate a contact as Economic Buyer):
```
manage_crm_objects(
  confirmationStatus: "CONFIRMED",
  updateRequest: { objects: [{
    objectType: "deals", objectId: <deal_id>,
    properties: {},
    associations: [{ targetObjectId: <contact_id>, targetObjectType: "contacts",
                     labels: ["Economic Buyer"] }]
  }]}
)
```
> The `hubspot-batch-create-associations` tool referenced in older docs does **not** exist on the current connector. The typeIds below are **REST-API-side reference** (RevOps scripts) — the connector never takes a typeId.

**Company → deal labels:**
| Label | typeId (REST reference) |
|---|---|
| Primary | 5 (auto on create) |
| End Customer | 78 — **required on every deal** |
| Reseller | 3 |
| Distributor | 80 |
| Paying Entity | 86 |
| Bidder / Bid Winner | 88 / 90 |
| Cloud Marketplace / Private Offer | 181 / 179 |
| Pro Serv Partner / Technology Partner | 92 / 9 |

**Contact → deal labels** — one contact per labeled type per deal; to move a label to a different contact, remove it from the first (UI).
| Label | typeId (REST reference) |
|---|---|
| (basic, unlabeled) | 3 |
| Champion | 82 (auto-fills `champion_v2`) |
| Economic Buyer | 7 (auto-fills `economic_buyer_v2`) |
| Billing Contact | 85 |
| Reseller Sales Rep | 11 |
| Pro Serve Partner / Technology Partner | 94 / 13 |
| Billing Escalation POC / Runner | 131 / 385 |
There is **no "Technical Contact" label** — associate a technical stakeholder as a basic contact (no labels) unless one of the labels above genuinely fits.

## 11. MEDDPICC contact-field status
`champion_v2` and `economic_buyer_v2` are **editable STRING fields** (corrected June 2026; not read-only/calculated as older docs claimed). They can be written directly, and they also surface the labeled contact's name when the Champion/EB label is applied. Prefer applying the label; write the string only if needed.

## 12. Competition enum (`competition`)
Predefined options only — no free text: Red Hat, CentOS, Oracle Linux, Alma Linux, Ubuntu, Suse, Self-Supported Rocky, Tux Care, Self Support, None, Rescale, HPE, ParallelWorks, NavOps by Altair. If the transcript names something off-list, pick the closest and note the limitation.

## 13. Product classes & categories
**Classes** (line item `class`): APPTAINER, ASCENDER PRO, BRIDGE, FUZZBALL, HPC, LTS, MANAGED SERVICES, ML KERNEL, MOUNTAIN, PROSERV, RLC, RLC AI, RLC HARDENED, ROCKYLINUX, SUPPORT, TRAINING, WAREWULF.
**Categories** (for deal naming, `product_category`): Apptainer, Ascender, Bridge, Fuzzball, HPC Stack, RLC, RLC-AI, RLC-H, Services (Recurring / Non-Recurring), WW Pro, Mountain.
These inherit from the product when the line item is product-linked — do not hand-set them (see `line_item_creation.md`).

## 14. Deal source & channel flag (set at creation — verified live 2026-07-08)
| Property | Values | Rule |
|---|---|---|
| `deal_source` | `Marketing` · `SDR` · `Sales` · `Partner Channel` · `Cloud BD` · `Unclear` | Ask as a tappable choice (or extract from transcript). Last-touch attribution to the deal — capturing it at birth is what makes attribution reporting possible later. |
| `channel_created_opportunity` | `true` / `false` | "Did this deal originate from a Channel Reseller?" — pairs naturally with the reseller question; set on reseller-originated deals. |
