# Line Item Creation — product-linked, never field-copied

This is the file that fixes the bug found on **2026-07-01** (Amit / Notified deal). Read it before Phase 4 step 5.
**The discount half of the bug RECURRED on 2026-07-02** (Infinite Campus, deal 62128438529: deal total $70,000 written into per-unit `discount` → −$13,880,000 rolled into `hs_arr`/`hs_tcv`/`net_new_arr` for a week — corrections log **D-13**). The "Discount arithmetic" section below is the binding rule: the skill computes the per-unit value from what the rep said; a rep's raw dollar figure NEVER goes into `discount` directly.

## The bug, in one sentence
Creating a line item as a bare object and **copying** the product's `hs_sku`, `class`, and `product_category` onto it as plain property values **does not work** — those fields silently reject the write and stay null — because in HubSpot they are populated only by the product→line-item **inheritance** that fires when the line item is created **linked to the product** (the same thing the UI does when you pick "Select from Product Library").

## What Amit's transcript PROVES (directly observed, high confidence)
- Writing `quantity`, `price`, `discount`, `hs_recurring_billing_period`, `recurringbillingfrequency`, `hs_product_type` on a hand-built line item **succeeded**.
- Writing `class`, `hs_sku`, `product_category` on that same line item **failed** — they never persisted.
- PATCHing `hs_product_id` onto the line item **after** it already existed **did not persist** (read-back showed it absent).
- `get_user_details` showed **object-level `LINE_ITEM` write was available the whole time** — so this is **not** a blanket permissions problem, despite the session concluding otherwise.
- The `discount` field is a **per-unit dollar amount, not a total**: setting `discount = 75000` on a `quantity = 1000` line item produced `(150 − 75000) × 1000 = −74,850,000`. The correct value was `discount = 75` per unit (50% of the $150 unit price) → net $75,000.

## The correct approach (follows from HubSpot's data model)
> ✅ **Status: VALIDATED LIVE in portal 22461953 on 2026-07-10** (RevOps, via the MCP connector — the exact path this skill uses). The primary mechanism below was run end-to-end on a throwaway deal: a line item created with ONLY `hs_product_id` (42387646054, RLC-PRO-STD) + `quantity` (200) + computed `discount` (250) **inherited all seven product fields** (`price` 600.00, `hs_sku`, `class`, `product_category`, `hs_recurring_billing_period`, `recurringbillingfrequency`, `hs_product_type`) with no manual set, and computed `amount` = exactly $70,000 = the target; the deal rollup populated `hs_tcv`/`hs_arr` = $70,000. Test objects deleted after verification. **Two facts learned:** (1) the fallbacks below were not needed — the primary mechanism just works; (2) deal-level `amount` does NOT auto-populate from line items (`hs_tcv`/`hs_arr` do) — set `amount` on the deal per `deal_setup_and_naming.md`.

**Principle:** a line item must be created **linked to the product**, not populated by copying the product's fields. When linked, HubSpot inherits `hs_sku`, `class`, `product_category`, `hs_recurring_billing_period`, `recurringbillingfrequency`, `hs_product_type`, and the unit `price` automatically.

**Supply only these fields at creation:**
- `hs_product_id` — the Active product's record ID (this is the link that triggers inheritance)
- `quantity`
- `discount` — **only if discounting**, as a **per-unit dollar amount** (unit_price × discount_fraction). Omit if no discount.
- association to the **deal** (so the line item rolls up into `hs_tcv`/`hs_arr`)

**Do NOT set** `hs_sku`, `class`, `product_category`, `hs_recurring_billing_period`, `recurringbillingfrequency`, `hs_product_type`, or `price` manually — let them inherit. (Setting them is what created a "custom-line-item-with-accurate-looking-values" that HubSpot then locked.)

**Primary mechanism to try first:** include `hs_product_id` in the `createRequest` properties for the `line_items` object, in the same call that associates it to the deal:

```
manage_crm_objects(
  confirmationStatus: "CONFIRMED",
  createRequest: { objects: [{
    objectType: "line_items",
    properties: {
      hs_product_id: "<active_product_record_id>",   # the link — triggers inheritance
      quantity: "<qty>",
      discount: "<per_unit_discount_dollars_or_omit>"
    },
    associations: [{ targetObjectId: <deal_id>, targetObjectType: "deals" }]
  }]}
)
```

**If `hs_product_id`-at-creation does not trigger inheritance** (validate first), try, in order:
1. Add a **products association in the same create call** — a second entry in the `associations` array: `{targetObjectId: <product_id>, targetObjectType: "products"}` alongside the deal association (created AT line-item creation time, not after) — then re-read to confirm inheritance. (Older docs named a `hubspot-batch-create-associations` tool for this; it does not exist on the current connector — see corrections D-11.)
2. **UI fallback (guaranteed correct):** direct the rep to add the product via the deal's Line Items → **"Select from Product Library"** → Active SKUs view (per the "Required Deal Properties" process). This is the path that has always worked; it is a fine answer when the API path is blocked, and far better than a line item with null identity fields.

## One-time validation test (run this before first production use, then delete the test line item)
1. Pick any Active product; note its `hs_price_usd`, `hs_sku`, `class`, `product_category`, billing fields.
2. On a throwaway/test deal, create a line item using the **primary mechanism** above (`hs_product_id` + `quantity` only).
3. Re-read the line item. **Pass** = `hs_sku`, `class`, `product_category`, `hs_recurring_billing_period`, `recurringbillingfrequency`, `hs_product_type`, and `price` all populated to match the product, with **no manual set**.
4. If pass → this protocol is confirmed; note the confirmation (with date) in the corrections log. If fail → try the fallbacks, record which one worked, and update this file.
5. While in the test deal, also confirm the **association labels** applied by name (End Customer / Champion / Economic Buyer) rendered correctly in the UI — the connector cannot read labels back (corrections D-11).
6. Delete the test line item / test deal.

## Discount arithmetic — THE SKILL DOES THE MATH (never pass a rep's raw number into `discount`)
HubSpot's `discount` is a **per-unit dollar amount** that gets multiplied by `quantity`. Reps never speak in per-unit discounts — they say "20% off," "sell it at $350/unit," or "**the deal needs to be $70K**." Writing any of those raw numbers into `discount` is the bug that produced **−$74.85M** (Notified, 2026-07-01) and **−$13.88M** (Infinite Campus, 2026-07-02, D-13). You must CONVERT the rep's intent to per-unit before writing:

| Rep says | Compute `discount` (per-unit $) |
|---|---|
| "X% off" | `round(price × X/100, 2)` |
| "sell at $S per unit" | `price − S` |
| "deal amount / ARR / ACV must be X" (annual value) | `round(price − X/quantity, 2)` |
| "TCV must be X over N years" | annual target `X/N`, then `round(price − (X/N)/quantity, 2)` |

- **ARR and ACV are the same annual number here; TCV needs the term** — if the rep gives a TCV target and the term isn't already known from the deal dates, ask for the term before computing. `amount` on an annually-billed line = the annual value.
- **Multi-line deals with one deal-level target:** ask the rep how to allocate (per-line targets), or propose a proportional split and get it confirmed — never guess a single line to absorb the whole discount.
- **Hard blocks (never write, escalate instead):**
  - `discount ≥ price` → line amount goes ≤ $0. Impossible-by-business-logic; you have almost certainly been handed a total, not a per-unit figure. Recompute; if the math genuinely yields this, STOP and re-confirm with the rep.
  - `discount < 0` (target above list price) → that is not a discount, it's non-standard pricing → **RevOps approval**, do not create.
- **Show the math in the Phase-3 summary BEFORE creating:** list price × qty, per-unit discount, and the computed line amount (`(price − discount) × quantity`), so the rep confirms the resulting total — e.g. "RLC Pro Standard: $600 × 200, −$250/unit discount → **$70,000/yr**".
- **Mandatory read-back assert after creating:** re-read the line item and check `amount > 0` **and** `amount` equals the rep's target within rounding tolerance (`quantity × $0.01`). If either fails, fix or delete the line item immediately — do not report success. (This single check catches every historical instance of this bug.)
- **Rounding:** if `target/quantity` doesn't land on a whole cent, the computed amount may differ from the target by a few cents — state the exact resulting amount to the rep rather than silently absorbing it.
- A discount > 0 requires **Sales Manager approval** (note it in deal notes); a genuine **custom SKU** or non-standard price requires **RevOps approval** — this skill does not create custom line items on its own.

### Worked examples (all real incidents or canonical)
- **Infinite Campus (the −$13.88M incident, D-13):** target deal value $70,000; RLC Pro Standard $600 × 200 units. `discount = 600 − 70000/200 = 250` → amount `(600−250)×200 = $70,000` ✓. (What was actually written: `discount = 70000` → `(600−70000)×200 = −$13,880,000`.)
- **Notified (the −$74.85M incident, 2026-07-01):** 50% off a $150 unit × 1000 → `discount = 75` → $75,000 ✓. (Written: `discount = 75000` → −$74,850,000.)
- **TCV target:** "3-year TCV of $300K" on a $500 unit × 250 → annual target `300000/3 = 100000` → `discount = 500 − 100000/250 = 100` → amount $100,000/yr, TCV $300K ✓.

## Why this matters downstream
A line item with null `hs_sku`/`class`/`product_category` is incomplete per Addendum A/C's own criteria, and a deal with no valid line items shows `hs_tcv = null` and `net_new_arr = 0` — invisible to ARR forecasting and flagged CRITICAL by the hygiene engine. Getting the line item right at creation is what keeps the deal out of the next hygiene report.
