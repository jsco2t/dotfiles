# Corrections Log — ciq-deal-creation

**Read this in full at Phase 0, before any tool call.** These are things prior versions of the deal instructions got wrong. Entries here **override** conflicting content anywhere else in the skill (including `references/ciq_reference.md`) and override your own priors. When the rep corrects something new, add a dated entry here in the same format rather than only fixing it in conversation.

**Entry format:** `D-<n> | <date> | <status> | <title>` → what was wrong → what's correct → evidence.

---

### D-1 | 2026-07-01 | ACTIVE (fix pending live validation) | Line items must be product-linked, not field-copied
- **Was wrong:** Deal Assistant v1.0–v2.2 Step 6 and Addendum A instructed creating a line item as a bare object and copying the product's `class`, `hs_sku`, `product_category` (and billing fields) onto it as plain properties.
- **Correct:** Create the line item **linked to the product** (`hs_product_id` at creation) and supply only `quantity` + `discount`; SKU/class/category/billing **inherit**. Do not hand-set them. See `references/line_item_creation.md` for the protocol, the one-time validation test, and the UI ("Select from Product Library") fallback.
- **Evidence:** Amit / Notified deal (2026-07-01). `class`/`hs_sku`/`product_category` writes silently failed; post-hoc `hs_product_id` PATCH didn't persist; `get_user_details` confirmed object-level LINE_ITEM write was available (so not a permissions issue). The corrected protocol is **not yet validated end-to-end in portal 22461953** — run the validation test and update this entry to CONFIRMED when it passes.

### D-2 | 2026-07-01 | CONFIRMED | `discount` on a line item is per-unit, not total
- **Was wrong:** Setting `discount` to the total discount amount.
- **Correct:** `discount` = **per-unit** dollar amount (unit_price × discount_fraction). Net = `(price − discount) × quantity`. Always verify by read-back.
- **Evidence:** Same deal — `discount = 75000` on `quantity = 1000` produced `−74,850,000`; correct value was `discount = 75` → net $75,000.

### D-3 | 2026-07-01 | ACTIVE | Validate SKUs against the live product record — never trust a plausible string
- **Was wrong:** Accepting a rep-provided SKU string as valid.
- **Correct:** Look up the product live, confirm `hs_status = active`, and match SKU + `hs_price_{currency}` + inherited fields. Surface any price discrepancy before proceeding.
- **Evidence:** Same deal — the SKU given was `Ascender-PRO-PRM`; the real Active SKU was `ASC-PRO-PRM`, and a decoy **inactive** SKU (`CIQASCPROPRM`) also existed. Only caught because Products access was later restored. (Both re-verified live 2026-07-08: `ASC-PRO-PRM` active at $150 USD; `CIQASCPROPRM` inactive.)

### D-4 | 2026-07-01 | CONFIRMED | Owner ID → name must be resolved live; specific mismaps to never repeat
- **Was wrong:** `CIQ_Sales_Operations_Reference_Data.md` hardcoded several owner names incorrectly.
- **Correct:** `329050336` = **David Horn** (never James Fitch) · `82821662` = **Suzanne Spencer-Purcell** (not "Dave Horn") · `251398025` = **Rose Stein** (HubSpot displays "Rose Samaniego") · `80484415` = **Derek Nolde, DEACTIVATED** (not active "Scott Nolde"). Always resolve live; the gotcha table in `ciq_reference.md` §9 is a verification layer only, and live data wins.
- **Evidence:** Cross-check of the project reference doc against the verified owners crosswalk. Hardcoded maps previously produced fabricated names in production (Tom Collins→"Tom Shingler", etc.).

### D-5 | 2026-07-01 | CONFIRMED | Stage probabilities diverge across systems — pull live, never hardcode
- **Was wrong:** Multiple docs hardcode a single "verified" probability set, but two sets disagree (Qualified 15 vs 20, Validate 24 vs 40, Propose 51 vs 60, In Procurement 83 vs 80).
- **Correct:** For any forecasting, pull `hs_deal_stage_probability` live per stage and check pipeline (Renewal shared stages carry higher probabilities). **Deal creation does not use probabilities** — new deals enter at Discovery — so this does not affect creation, but the conflict must not be "resolved" by picking a table.
- **Evidence:** Addendum C / hygiene / pipeline docs vs. the FY26 preferences reference; also flagged in RevOps memory (values diverged Feb 8 vs Mar 10 2026).

### D-6 | 2026-07-01 | CONFIRMED | Renewal pipeline stage names were changed
- **Was wrong:** Docs list `125777760/761/762` as "90/60/30 days to Renewal."
- **Correct:** `125777760` = Outreach Required · `125777761` = Renewal Initiated · `125777762` = Propose & Negotiations. IDs unchanged, labels changed.
- **Evidence:** RevOps memory + FY26 preferences reference.

### D-7 | 2026-06-22 | CONFIRMED (mechanism updated by D-11) | Contact-association labels DO work via API
- **Was wrong:** v1.0–v1.1 (and Deal Hygiene v1.1) said Champion/EB and other contact labels are UI-only and `champion_v2`/`economic_buyer_v2` are read-only/calculated.
- **Correct:** Labeled associations work programmatically — one contact per labeled type per deal. `champion_v2` and `economic_buyer_v2` are **editable strings**. On the current native connector the mechanism is label **names** (see D-11), not typeIds.
- **Evidence:** Deal Assistant v2.2 changelog (2026-06-22), verified against live portal.

### D-8 | 2026-06-22 | CONFIRMED | `professional_services_deal` has both Yes and No
- **Was wrong:** "Only Yes exists; leave blank = No."
- **Correct:** Set `professional_services_deal` explicitly to Yes or No.
- **Evidence:** Deal Assistant v2.2 changelog; re-verified live 2026-07-08 (`get_properties`: options Yes + No).

### D-9 | 2026-07-01 | CONFIRMED | `hs_is_closed = false` includes Won-stage deals — don't use it to define "open," never re-date a Won deal
- **Was wrong:** Old docs (Deal Hygiene v1.1, Deal Assistant v2.2, Pipeline Analytics v2, CIQ_Sales_Operations) and `ciq-hygiene-manager` define "open deals" as `hs_is_closed = false`.
- **Correct:** HubSpot reports `hs_is_closed = false` on the Sales **Won** stage (`93217107`, won-awaiting-finance-booking, before terminal Closed Won `143973802`). Define "open" by **excluding the Won + closed stage IDs explicitly** (Sales `93217107`/`143973802`/`93217108`; Renewal `125777763`/`125777764`/`125777765`). **Never edit `closedate` on a Won/closed deal** — it's the actual booked date. Renewal-Won `hs_is_closed` behavior is undocumented; verify before relying on it.
- **Evidence:** `ciq-deal-hygiene` reference files document this (Won-stage deals "report `hs_is_closed=false` but are terminal") and its corrections #38 (a hygiene run that didn't honor this closed-lost two Closed-Won deals). Rakuten Bridge Expansion (Sales-pipeline Won deal) had its close date changed after being pulled as "open." `ciq-deal-hygiene` already drops Won-stage deals at fresh-read; `ciq-hygiene-manager` and Pipeline Analytics v2 do **not** yet — the manager skill still needs the same exclusion (pipeline reporting is now covered by `ciq-pipeline-analytics`, which uses an open-stage whitelist).

### D-10 | 2026-07-08 | OPEN (RevOps decision pending) | `ascender_se = 432367417` is an owner ID written into a user-enum field
- **What's off:** `ascender_se` is a HubSpot user-type enumeration. Its live option list (50 users) includes **neither** `432367417` (Jimmy Conner's OWNER id) **nor** his user id (`51990024`) — Jimmy is not currently a valid option for the field at all. The API accepts the out-of-enum write, and 80+ existing deals carry `432367417` (recent creations included), but the value may not render as a person in the UI and won't match option-keyed filters. Other deals carry legitimate user-id values (e.g. `82186108` Tommy Yi) — the field holds mixed ID spaces today.
- **Interim rule:** keep writing the convention value `432367417` (consistency with the existing book + the SOP) — do NOT improvise a different ID.
- **Resolution owner:** RevOps — either restore Jimmy as a valid option / pick the current Ascender SE and backfill, or bless `432367417` as a deliberate owner-id convention and document it.
- **Evidence:** Live `get_properties(deals, ascender_se)` option list + live deal sample (both 2026-07-08); `inx` owner crosswalk (432367417 = Jimmy Conner owner_id, user_id 51990024).

### D-11 | 2026-07-08 | CONFIRMED | Current connector: associations + labels via `manage_crm_objects` label NAMES; `hubspot-batch-create-associations` does not exist
- **Was wrong:** v1.0 skill text and older docs gave association patterns calling a `hubspot-batch-create-associations` tool with `associationCategory`/`associationTypeId` parameters.
- **Correct:** The current native HubSpot connector has no such tool. Associations are created on the `associations` array of `manage_crm_objects` create/update calls; labels are applied by **NAME** (`labels: ["End Customer"]`, `["Champion"]`, `["Economic Buyer"]`); omitting `labels` yields the default association; labels must already exist for the object-type pair. TypeIds remain valid for the REST API (RevOps scripts) only. The connector cannot READ labels back — confirm applied labels in the HubSpot UI during the one-time validation run.
- **Evidence:** Live `manage_crm_objects` tool schema (AssociationContext: `targetObjectId`/`targetObjectType`/`labels[]`), inspected 2026-07-08; current connector tool inventory (no batch-associations tool).

### D-12 | 2026-07-08 | OPEN | `deal_creation_feedback` property does not exist yet
- **What's off:** Phase 6 wants rep feedback appended to a `deal_creation_feedback` deal property, mirroring the hygiene skill's `hygiene_feedback`. Verified 2026-07-08: the property does not exist in portal 22461953 (`hygiene_feedback` does).
- **Interim rule:** capture feedback in the corrections-log entry format in chat and tell the rep it's logged for RevOps; do NOT invent the property.
- **Resolution owner:** RevOps — create `deal_creation_feedback` (clone the `hygiene_feedback` definition: append-only JSON array), then this entry flips to CONFIRMED and Phase 6 writes to it.
- **Evidence:** Live `search_properties(deals)` 2026-07-08.

### D-13 | 2026-07-10 | CONFIRMED | Deal total written into per-unit `discount` → −$13.88M deal (Infinite Campus) — the skill must COMPUTE per-unit discounts
- **Was wrong:** The line-item write on deal `62128438529` ("Infinite Campus - RLC - New Business - 2026", created 2026-07-02 17:36 UTC via the connector, INTEGRATION 16228553) set `discount = 70000` — the intended DEAL TOTAL — on a `price = 600 × quantity = 200` line. HubSpot's `discount` is per-unit: `amount = (600 − 70000) × 200 = −13,880,000`, which rolled into the deal's `hs_arr`/`hs_tcv` and (via the portal's net-new automation, AUTOMATION_PLATFORM ~10s later) into `net_new_arr`. The poison lived 2026-07-02 → 2026-07-09 22:45 UTC, when Tabatha fixed it manually (`discount = 250` → $70,000 ✓). Same failure class as the 2026-07-01 Notified −$74.85M incident (documented in `references/line_item_creation.md`) — which had not yet shipped in the deployed skill when this deal was created.
- **Correct:** The skill converts the rep's stated intent to the per-unit figure — "X% off" → `price×X/100`; "sell at $S/unit" → `price − S`; "deal amount/ARR/ACV must be $X" → `price − X/quantity`; "TCV $X over N years" → `price − (X/N)/quantity`. A rep's raw dollar figure NEVER goes into `discount`. Hard blocks: computed `discount ≥ price` (amount ≤ 0 — you were handed a total) and `discount < 0` (above-list → RevOps approval). Mandatory read-back assert after create: `amount > 0` AND `amount` = target ± `quantity × $0.01`.
- **Evidence:** Line item `56846095244` propertiesWithHistory (`discount`: 70000 INTEGRATION/16228553 2026-07-02 → 50000 CRM_UI/76138901 → 250 CRM_UI/76138901 2026-07-09; `amount`: −13,880,000 → −9,880,000 → 70,000); deal `62128438529` `net_new_arr` history (AUTOMATION_PLATFORM mirroring each value). Portal-wide sweep 2026-07-10: no other negative-amount line items from this vector (3 unrelated −$200 Quotes-tool artifacts, Jan 2026); connector-created line items since v1.1 (2026-07-08) all carry `discount = None`.

### D-14 | 2026-07-10 | CONFIRMED | Line-item protocol VALIDATED live (one-time test run + passed); deal `amount` does not roll up
- **What was open:** `references/line_item_creation.md` carried "Status: corrected protocol, pending live validation in portal 22461953" since 2026-07-01 — the product-link inheritance recipe had never been run end-to-end through the connector (D-1 follow-through).
- **Now confirmed:** Run 2026-07-10 by RevOps on a throwaway deal (created + deleted same session). Line item created with ONLY `hs_product_id` + `quantity` + computed `discount` via `manage_crm_objects`: all 7 product fields inherited (price/hs_sku/class/product_category/billing period/frequency/type), `amount` computed to exactly the target ($70,000 from price 600 × qty 200 − discount 250), deal rollup `hs_tcv`/`hs_arr` populated. Fallback paths not needed. ALSO LEARNED: deal-level `amount` does NOT auto-populate from line items (`hs_tcv`/`hs_arr` do) — the skill must set deal `amount` itself per `deal_setup_and_naming.md`.
- **Evidence:** Test deal 62489885293 + line item 56950614277 (both archived after read-back verification, 2026-07-10 ~18:33 UTC).
