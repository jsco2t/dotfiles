# Connector mapping (Claude desktop/web — MCP)

This skill runs through the **HubSpot and Fathom connectors** (no local scripts/tokens). Single-rep scope.

## HubSpot — Step 0: detect your tools; the rep connector is usually READ-ONLY
**Before anything, see which HubSpot tools you actually have, then branch. Do not hunt or stall.**
The rep-facing connector commonly exposes a **single read-only** tool — `query_crm_data` (SELECT-only SQL). A
richer connector also exposes `search_crm_objects`, `get_crm_objects`, `search_owners`, `get_properties`, and the
**write** tool `manage_crm_objects`.
- **Only `query_crm_data` is present →** read-only mode: do all reads via SQL (below); run Phases 1–4 and **draft**
  every fix (Phase 5 hands back exact values to apply — no direct writes). This is expected, not an error.
- **`manage_crm_objects` is present →** full mode: read via `search_crm_objects`/`get_crm_objects` (or SQL), apply writes via `manage_crm_objects`.

### Reading with `query_crm_data` (the read-only SQL surface)
**Call the connector's Tool Guidance first** (it's required and has the exact syntax). Constraints: one object type per
query (`DEAL`/`COMPANY`/`CONTACT`/`LINE_ITEM`); **AND-only** (no OR/LIKE/JOIN/CASE/DISTINCT); text via
`KEYWORD_SEARCH_QUERY('term','prop')`; dates via `BETWEEN 'YYYY-MM-DD'`; cross-object via `OBJECT.property`
(e.g. `SELECT COMPANY.notes_last_contacted FROM DEAL …`, max 2 associated types). Property names come from
`reference_data.md` (you can't call `search_properties` on the thin connector).
- **Scope gate:** `Missing required scope: reporting-base-read` → the rep must enable "Query portal data"; without it there is **no** read path. Never fabricate.
- **Your deals:** `FROM DEAL WHERE pipeline='45314112' AND hs_is_closed=false AND hubspot_owner_id='<id>'`.
- **Company-sweep (D003):** add `COMPANY.notes_last_contacted`, `COMPANY.hs_last_sales_activity_timestamp`, `COMPANY.domain` to that query (cross-object).
- **Line items (D006):** `FROM LINE_ITEM WHERE DEAL.hubspot_owner_id='<id>' …` selecting `hs_arr, recurringbillingfrequency, hs_product_type, amount`.
- **Domain-match (D005):** `FROM CONTACT WHERE KEYWORD_SEARCH_QUERY('@<domain>','email')` selecting `email, notes_last_contacted, hs_last_sales_activity_timestamp`.
- **Owner id:** for **your own** run, resolve via the current-user owner (Tool Guidance). For a **named** rep (manager run), the read-only connector has **no owner search** — ask for that rep's `hubspot_owner_id` rather than guessing.

### Pull A — your open Sales deals (foundation)
`FROM DEAL WHERE pipeline = '45314112' AND hs_is_closed = false AND hubspot_owner_id = '<your id>'`,
selecting the full property set in `reference_data.md`. (Renewal 49231982 only if you ask; never Alt 793851464.)

### Pull B — line items
Per deal, the line items (name, hs_product_type, recurringbillingfrequency, price, quantity, amount, hs_arr, class) — for the ARR/line-item checks.

### Pull C — associations (labels)
Per deal: companies (is there an End Customer 78? a Reseller 3 / Distributor 80?) and contacts (count, and whether Champion 82 / EB 7 labels exist). Labels need the label-aware association read; if the connector can't see labels, use `champion_v2`/`economic_buyer_v2` as proxies and note the limit.

### Pull D — engagement (account-aware staleness)  ← the key one; was SKIPPED in the live test
Staleness must be **account-wide**, not deal-only, and you MUST fetch the **company record** (skipping it caused the
false "Pfizer dark 99d" — the company record showed May 18). For each deal:
- the deal's `notes_last_contacted`;
- each associated **contact's** `notes_last_contacted` / `hs_last_sales_activity_timestamp`;
- the **End-Customer company's** `domain`, `notes_last_contacted` / `hs_last_sales_activity_timestamp`, and recent engagements;
- **domain-matched contacts (D005):** search HubSpot contacts by `email CONTAINS_TOKEN '@<company domain>'`; include any
  contact on the End-Customer domain in the staleness calc **even if unassociated**, and surface unassociated ones to
  associate to the deal. Exclude generic domains (gmail.com, outlook.com, yahoo.com…).
- **cross-functional CIQ contacts (D010):** PS/CSM/eng or contacts active on sibling deals at the same account → context (not dark).
`true_last_contact = most recent of {deal, associated contacts, company, domain-matched contacts}`. Classify:
**account-dark** (all silent >30d), **off-deal** (account/domain active ≤30d but not on the deal → associate), or active.
For flagged deals also pull recent email bodies (`hs_email_html` + `hs_email_direction`: `EMAIL`=outbound,
`INCOMING_EMAIL`=customer) for response-rate, cadence, stall-language, and commitments.

### Pull E — upcoming / scheduled meetings
Pull **meeting engagements with a future start time** associated to the deal and its contacts (HubSpot Meetings —
e.g. `hs_meeting_start_time >= today`, or the connector's engagements/meetings read). A booked next meeting is
**forward motion**: surface it, source the Next Step from it, and don't treat the account as dark. Its absence on an
active (Validate+) deal is a **momentum risk**. A *past* scheduled meeting with no recording/outcome logged = a **logging gap**.

## Fathom (deep-pull — retention is UNLIMITED)
Do NOT conclude "no coverage" from a shallow search. To reach full history:
- `find_person` on each stakeholder (exact spelling; try full name AND last name — e.g. "Harald" not "Harry");
- `search_meetings` with `recorded_by:"anyone"`, `max_pages:20`, on company + deal keywords;
- `list_meetings` paginated **backward** with `created_before` (step back by months) to reach older meetings;
- open `get_meeting_transcript` for the best matches; cite `recording_id` + verbatim quotes.
Use Fathom to verify qualification (is the buyer/decision-process actually discussed?) and post-meeting follow-up.

## Slack (recommended — deal-channel search, D008)
- For **Validate+ / active-POC** deals, search for a **deal- or company-named channel** (e.g. `#ciq-<company>`) via
  `slack_search_channels` / `slack_search_public`; if found, read it for trial status, success criteria, and who's
  engaged, and fold that into the engagement picture + Next Step (don't flag dark when a POC channel is active).
- Also `slack_search_public` for company/deal/stakeholder mentions. Ask consent before any private search.

## Writes (the Fix-it-now workstream) — ONLY if a write tool is present
**If `manage_crm_objects` is not in your toolset (the usual rep case — the connector is read-only `query_crm_data`),
you cannot write. Run read-only and hand back every fix as a drafted value + the exact apply path. Do NOT stall
hunting for a write tool, and do NOT conclude the skill is broken — read-only is an expected mode.**
When `manage_crm_objects` IS present: every write needs **explicit per-deal approval** — call it **by name** (the
write tool is not named "write/create/update"); read the current value first, write, then read back and confirm:
- **Property updates** — `hs_next_step`, MEDDPICC text fields, `dealstage`, `closedate`. **APPEND** to
  `hs_next_step` and MEDDPICC (read current → add to it → write; never overwrite). `competition` must be a
  valid enum value (see `reference_data.md`). Confirm `dealstage`/`closedate` changes explicitly — they move the forecast.
  **⛔ `dealstage` may ONLY be a forward advance among OPEN stages, and `closedate` only on an OPEN deal (golden rule 12 /
  D-39).** NEVER write `dealstage` to a closed stage (Closed Won `93217107`/`143973802`, Closed Lost `93217108` Sales /
  `125777765` Renewal), NEVER reopen a closed deal, and NEVER write to any deal where `hs_is_closed=true`. Close/lose/win/reopen
  is the rep's manual HubSpot-UI action (where pipeline approval / closed-edit rules apply; the API path here bypasses them).
- **Champion / Economic Buyer (yours)** — once you've identified the person from the
  evidence: make sure the contact is **associated to the deal**, then set the labeled association —
  Champion = contact→deal label **82**, Economic Buyer = **7**. If the connector's association tool can't
  set a label, hand back the manual path: open the deal → **Contacts** card → add/associate the contact →
  set its **role** to Champion / Economic Buyer.
- **Line items (yours — the connector writes these directly)** — create/update line items via
  `manage_crm_objects` on the `line_items` object and associate them to the deal. To fix **$0 ARR**, set
  `recurringbillingfrequency` (e.g. `annually` / `monthly`) on the subscription line so `hs_arr` computes; to
  fix an **amount ↔ line-items** gap, correct the line-item `price` / `quantity` or add the missing SKU
  (prefer `hs_product_id` from the product library so the SKU/taxonomy is right — don't edit `amount` to match).
  Read the deal's current line items first, confirm SKU/price/term with the rep, write, then read back and
  confirm `hs_arr` / `hs_tcv` recomputed. (Don't "fix" legitimate $0 — POC / PS / embedded.)

- **Deal hygiene stamp (write these, not the object)** — on each deal you review/fix, set `hygiene_score` (per-deal
  cleanliness 0–100, formula in `run_record.md`), `last_hygiene_score_date` (today), and `blockers` (the blocker or
  "none"). These are ordinary deal-property writes the connector supports.
- **Do NOT write the `Hygiene Run` object** (`2-63704277`). The browser connector can't create custom-object records, and
  that object is owned solely by the **twice-daily server-side batch** (`scripts/score_all_reps.py`) — the authoritative
  writer of rep scores, trend, and the differential report. Reps/managers **read** it; they never create records in it.

Off-deal re-association and cross-deal dedup are **also yours** — flag/apply them on the same per-deal approval. No separate
RevOps bucket. **Company-association LABELS (End-Customer 78 / Reseller 3 / Distributor 80) are NOT yours** — the connector
can't read association typeIds, so the **twice-daily batch** handles them (reads typeIds via REST, auto-tags the obvious
End-Customer, flags only the ambiguous). You still apply **Champion/EB contact labels** (82/7) — those are contact labels, not
company-association typeIds.
