# Deal Setup, Naming & Structure

## Required properties (hard blocks — cannot create without these)
Company identified · at least 1 valid line item · close date · deal type · term start + term end · `reseller_deal` set (true/false) · `deal_source` set · Next Step · End Customer association ready · explicit "Create the deal".

| Property | Internal name | Notes |
|---|---|---|
| Deal name | `dealname` | see naming convention below |
| Deal type | `dealtype` | `newbusiness` / `existingbusiness` / `Expansion` / `Overages` |
| Pipeline | `pipeline` | auto from deal type (see ciq_reference §6) |
| Deal stage | `dealstage` | auto: Discovery `93217102` or Upcoming Renewals `125777759` |
| Close date | `closedate` | ISO `YYYY-MM-DDTHH:MM:SS.000Z`; forward-looking |
| Owner | `hubspot_owner_id` | owner **ID**, resolved live — **defaults to the creating rep**; on-behalf creation requires the rep to name the owner explicitly |
| Currency | `deal_currency_code` | USD/EUR/KRW/JPY |
| Deal source | `deal_source` | Marketing / SDR / Sales / Partner Channel / Cloud BD / Unclear (tappable — see ciq_reference §14) |
| Channel-created | `channel_created_opportunity` | `"true"` / `"false"` — set on reseller-originated deals |
| Term start / end | `term_start` / `term_end` | `YYYY-MM-DD` |
| Term length | `length_of_term__months_` | **calculated** = (end.year−start.year)*12 + (end.month−start.month) |
| Reseller deal | `reseller_deal` | `"true"` / `"false"` — required |
| Expansion+Renewal | `renewal__expansion` | only when `dealtype = Expansion` |
| Ascender SE | `ascender_se` | `432367417` if any line item category = Ascender (⚠ see below + corrections D-10) |
| Identified Pain / Competition / Metrics / Next Step | see bant_and_meddpicc | MEDDPICC at Discovery |

Financial fields (`hs_tcv`, `hs_acv`, `hs_arr`, `net_new_arr`, `amount_in_home_currency`) are **read-only/calculated from line items** — never set them manually. When line items exist, `amount` should equal `hs_tcv`. Terminology: ACV = contract value normalized to 12 months, ARR = recurring revenue normalized to 12 months, TCV = full-term total — for a 12-month contract all three are equal; multi-year → TCV > ACV.

**The deal-level `products` field is populated by a HubSpot workflow** from line-item `product_category` within ~1–2 minutes of creation — never set it directly; tell the rep what it should show.

## Naming convention
`[Company] - [Product Category] - [Deal Type] - [Year]`
- Company: exact HubSpot name (smart-abbreviate only very long org names — "Sandia National Laboratories" → "Sandia", "…NOAA…" → "NOAA").
- Product Category: from the line item's `product_category` (not the full product name); if multiple, use the primary/highest-value one.
- Examples: `Advance Auto Parts - RLC - New Business - 2026` · `Notified - Ascender - New Business - 2026` · `Sandia - WW Pro - Renewal - 2025`.

## Term dates
Standard term is 12 months. For a start of `9/9/2026`, a 12-month term ends `9/8/2027` (ending the day before to avoid renewal overlap) — confirm with the rep if they want an exact `9/9/2027` instead. Always auto-calculate `length_of_term__months_`; don't ask the rep to compute it.

## Company association structure
Every deal needs **Primary** and **End Customer** (labels applied by name — ciq_reference §10).
- **Direct deal:** the same company gets both Primary and End Customer.
- **Reseller deal:** Reseller/Distributor company → Primary + "Reseller" (or "Distributor") label; the end-user company → "End Customer". Add "Paying Entity" if the payer differs.

## Professional Services field
`professional_services_deal` now has **both "Yes" and "No"** options (the old "only Yes exists, leave blank = No" workaround is retired) — set it explicitly.

## Payment terms (from RevOps SOP)
- **Net 30** = default, no approval. **Net 45** = allowed, no approval. **Anything else** (including terms beyond Net 45, foreign-reseller extended terms, gov/public-sector specifics) = **RevOps approval required**; note it in the deal record.
- Resellers: **PO always required**, and the PO must reference the quote number.

## SKUs, discounts, custom line items
- **Active SKUs only** (`hs_status = "active"`, not `sku_status`). Never add deprecated/inactive SKUs.
- A genuine **custom line item** or **non-standard price** requires **RevOps approval** — this skill does not create custom SKUs on its own.
- Any **unit discount** requires **Sales Manager approval**; document it in deal notes. Discount is entered as a **per-unit dollar amount** (see `line_item_creation.md`).
- **University exception:** Warewulf Pro for universities is **not** subject to the $10K minimum order.

## Ascender SE auto-assign
If any line item's `product_category` is Ascender, set `ascender_se = 432367417` (Jimmy Conner) — the established org convention, carried by 80+ existing deals.
> ⚠ **Known issue (corrections D-10, decision pending):** `432367417` is Jimmy Conner's *owner* ID, but the `ascender_se` field is a user-enum whose live option list includes neither that value nor his user id. The API accepts the write, but the value may not render as a person in the UI. Keep writing the convention value until RevOps resolves the field — do not improvise a different ID.

## Contact creation (search first, then don't defer)
**Search before creating** — by name, email, AND the company's domain. A person often already exists under a personal/Gmail identity (conference badge scans); if a likely twin exists, use it and flag the additional email for RevOps to add as a secondary — don't create a duplicate. If genuinely absent, **create the contact immediately** and associate it to the company (extract title/role from the transcript), then associate to the deal with the right MEDDPICC label. Do not tell the rep to create contacts manually.
