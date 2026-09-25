# Fix-it-now playbook — apply each fix in-session

The report is only half the job. After presenting the findings, **offer to fix the deals with the rep, one
at a time**, and apply each approved change through the HubSpot connector. Read-only is the default — nothing
is written without the rep's explicit per-deal approval. Every change cites the evidence behind it (Principle 0).

## The loop (per deal, worst-first)
1. Show a short fix checklist for the deal — each item: what's wrong, the drafted value, and its source.
2. Rep approves which to apply (all / some / none).
3. Apply each via the connector: **read the current value first, write, then read back and confirm** what changed.
4. Re-check the deal and move to the next.

Forecast-moving changes (`dealstage`, `closedate`) need an explicit "yes" each time. Text fields are
**appended**, never overwritten.

> **⛔ Hard limit (golden rule 12 / D-39): this skill NEVER closes, loses, wins, reopens, or re-stages a deal into/out of a
> closed stage, and NEVER writes to a deal where `hs_is_closed=true` OR where the deal is in a Won stage.** Won deals
> (`93217107` Sales **Won** / `1162796937` Alt **Won** — note: `93217107` is "Won", NOT "Closed Won"; `143973802` is Closed Won)
> and closed deals are dropped at fresh-read and are never in this loop. A `dealstage` write is permitted ONLY as a **forward
> advance among OPEN stages** on an explicit yes — never to/at/past a Won stage (`93217107` Sales Won / `1162796937` Alt Won)
> or a Closed Won stage (`143973802` Sales / `125777763`/`125777764` Renewal) or Closed Lost (`93217108` Sales / `125777765`
> Renewal). **Never write to a deal already in a Won stage (`93217107`/`1162796937`), even when `hs_is_closed=false`** — these
> are terminal wins (PO received, awaiting finance booking). If the rep wants to close/lose/win/reopen a deal, tell them to do
> it in the **HubSpot UI** (the pipeline's approval and closed-edit rules apply there; the connector's API path bypasses them,
> so it must not perform these moves).

## By issue type

### Next Step (empty or stale)
- Draft a dated entry: `MM.DD.YY [initials] — <what happened> → <specific next action + date/owner>`.
- **APPEND** to `hs_next_step` (read current → add the new line on top → write). Never erase prior history.

### MEDDPICC thin
- Draft the missing substance for the thin field (pain / metric / decision criteria / decision process /
  paper process), grounded in a specific call or email — cite it.
- **APPEND** to the specific field (e.g. `decision_process_v2`); never overwrite. `competition` must be a
  valid enum value (see `reference_data.md`).

### Champion / Economic Buyer  (identify → associate → label — this is the rep's)
1. **Identify** the person from your own evidence: transcripts (who drives the decision / controls budget),
   notes, and email bodies. State who, and cite where (recording id / email).
2. **Associate** that contact to the deal if they aren't already (the deal's Contacts card).
3. **Label** the association: Champion = contact→deal label **82**, Economic Buyer = **7**.
   - Via connector: set the labeled association on the contact↔deal pair.
   - Manual fallback: open the deal → **Contacts** → the person → set **role** = Champion / Economic Buyer.
4. This populates `champion_v2` / `economic_buyer_v2`. It does **not** change qualification — that's still the
   MEDDPICC text. An empty label was never an "unqualified" verdict, just an unapplied label.

### Stage stalled / ready to advance
- If MEDDPICC depth already meets the **next** stage's bar and line items exist → propose advancing; on an
  explicit "yes," set `dealstage` **to the next OPEN stage only**. If it's stalled with no motion, the real fix is a concrete
  Next Step + re-engagement, not a stage change.
- **Never advance a deal to/past a Won stage or a closed stage, and never re-stage a closed deal** — winning/losing/reopening is the
  rep's manual HubSpot action, not a hygiene write (golden rule 12 / D-39).
- **Never write to a deal already in a Won stage (`93217107` Sales Won / `1162796937` Alt Won), even when `hs_is_closed=false`** — these are terminal wins (PO received, awaiting finance booking). Drop them at fresh-read; do not analyze, flag, or write to them.

### Close date in the past
- Propose a realistic **future** `closedate` from the actual motion **on an OPEN deal**; set it on approval. (D-40: this is the **close-coherence WARNING** - re-dating the OPEN deal clears it; an early-stage deal closing <=30d out is a **CRITICAL** coherence flag. It counts toward forecast-at-risk, but a past date is still never "overdue -> close it lost.") **A past close date is never a reason to close the deal lost** — if it's truly dead,
  tell the rep to close it lost themselves in HubSpot; this skill does not (golden rule 12 / D-39).

### Line items / $0 ARR  (yours — the connector writes line items directly)
1. Read the deal's current line items first (name, `hs_product_type`, `recurringbillingfrequency`, `price`,
   `quantity`, `hs_arr`).
2. Apply via the connector (`manage_crm_objects` on `line_items`, associated to the deal):
   - **$0 ARR on a subscription line** → set `recurringbillingfrequency` (e.g. `annually` / `monthly`) so `hs_arr` computes.
   - **Amount ↔ line-items gap** → correct the line-item `price` / `quantity`, or add the missing SKU — prefer
     `hs_product_id` from the product library so the SKU/taxonomy is right (don't edit `amount` to match).
   - **Missing line items at stage** → add the products the deal is actually selling.
3. Confirm SKU / price / term with the rep before writing; read back and confirm `hs_arr` / `hs_tcv` recomputed.
- **Don't "fix" legitimate $0:** POC, embedded/OEM, and Professional-Services / Service / Product lines are
  correctly non-recurring.

### Term dates
- If `term_start` / `term_end` / `length_of_term__months_` disagree on a **positive** span, confirm the right
  dates with the rep and set them. Never touch `closedate > term_start` (normal for co-term / expansion).

### Blockers (always — `blockers` open-text property)
On every deal you update, set the dedicated **`blockers`** property: the current blocker in plain text (e.g. "awaiting
customer security review; legal redlines open") or **"none"**. Don't bury a blocker in the Next Step — `blockers` is its
own searchable field. Read current → set (overwrite is fine; it's a current-state field, not an append-log). (DD-7)

### Feedback (when the rep disputes a flag — append to `hygiene_feedback`)
The rep is always right to dispute — never defend a flag. Capture it on the deal so RevOps can mine it later:
1. **Read** the deal's current `hygiene_feedback`. Parse it as a JSON array; if empty/blank, start `[]`.
2. **Append** one item: `{"ts":"<ISO>","skill_version":"v2.9","feedback_type":"false_positive|wrong_value|missing|wrong_owner|ux|other","check":"<which check>","skill_output":"<what the skill claimed, verbatim>","rep_correction":"<rep's exact words / correct value>","evidence":"<recording id / email / field>","status":"new"}`.
3. **Write** the full array back to `hygiene_feedback` (overwrite the property *value* with the appended array — but never drop existing items). This is an append-to-array, not an erase.
Interim capture only (reps can't write the `Hygiene Run` object); RevOps parses `hygiene_feedback` across deals once the
scalable feedback architecture is decided. Don't editorialize — record the rep's correction verbatim (a rep can be wrong too; verification happens later, Principle 0).

### Hygiene stamps are BATCH-OWNED — do not write them (changed in v4.6, D-52)
Do **not** write `hygiene_score` or `last_hygiene_score_date` — the batch stamps every open deal on each run and is
the only writer (the skill-side recompute this section used to describe added arithmetic-drift risk for no benefit).
After fixes land, tell the rep: the score refreshes at the next batch run, and tomorrow's report opens with a
**"Since the last report"** section confirming exactly which flags cleared. You also do **not** write the
`Hygiene Run` object (the batch owns that too).

### Note describes a meeting that was never logged → create the Meeting
The report flags a `log_meeting` recommendation when a recent note body describes an in-person meeting, call, or customer visit that has no matching Meeting or Call engagement on the deal.

**Procedure (always gate on rep confirmation — never fabricate):**
1. **Read the note body** — use `get_crm_objects` to pull the full engagement body for the flagged note. If a Fathom meeting link or recording id appears in the note, pull the summary/transcript via the Fathom connector to surface participants and details.
2. **Confirm with the rep** — present what the note says and ask the rep to confirm: the meeting date, who attended (contact names/roles), and the outcome/summary. If any detail is unclear or unconfirmed, ask — **never assert a name, date, or outcome not explicitly in the note or confirmed by the rep.**
3. **Create the Meeting engagement** — once the rep confirms, use `manage_crm_objects` with object type `meetings` and at minimum:
   - `hs_meeting_title` — a short descriptive title ("Onsite — [Customer Name] — [Date]")
   - `hs_meeting_start_time` — ISO 8601 timestamp from the rep-confirmed date
   - `hs_meeting_outcome` — one of `SCHEDULED` / `COMPLETED` / `NO_SHOW` / `CANCELLED` / `RESCHEDULED` (use `COMPLETED` for a past meeting)
   - `hs_internal_meeting_notes` — the outcome/summary the rep confirmed, cited from the note
4. **Associate to the deal** — associate the new Meeting engagement to the deal via the HubSpot connector.
5. **Associate to the relevant contacts** — associate the Meeting to each confirmed attendee contact. Do not add contacts not confirmed by the rep.
6. **Cite the source note** — record the note engagement id in your confirmation message so RevOps can audit the lineage.
7. **Confirm with a re-read** — read back the new engagement to confirm it landed with the correct date and outcome.

> **Golden rule 1 applies in full:** every field of the Meeting comes from the note body, the Fathom transcript, or the rep's explicit confirmation. If you cannot verify a participant's name, date, or outcome, do NOT fill the field — ask the rep. A blank field is better than a fabricated one.

### Multi-threading (dark-after-pricing, single-threaded)
The report flags a `multithread` recommendation when a deal is dark after a pricing conversation AND single-threaded (fewer contacts than the stage requires). This is a **coaching question**, not an automated action.

**What to do:**
1. **Surface the report's coaching question** to the rep verbatim: *"This deal went dark after pricing and you're currently single-threaded. Who else in the org should you be talking to? Consider researching the org chart for a stakeholder above your current buyer, or ask Marketing to enroll other known contacts in a nurture campaign."*
2. **You may name a known sibling-deal contact** (e.g. a contact the report flagged from a related deal at the same company) as a *possible lead to research* — always framed as a suggestion, never as a confirmed stakeholder. Cite where the name came from.
3. **Suggest next actions the rep can take manually:**
   - Pull the account's org chart (LinkedIn, ZoomInfo) for a decision-maker or economic buyer above the current contact.
   - Coordinate with Marketing to enroll known domain contacts in an Ascender / RLC nurture sequence.
   - Revisit the deal's MEDDPICC Economic Buyer field — if the EB is unidentified, that is the gap to close first.

> **⛔ This skill does NOT create, associate, or contact any new contact for multi-threading.** The coaching question is the output. All contact decisions belong to the rep (and any nurture coordination belongs to Marketing). Do not add any contact to the deal, do not send any outreach, and do not write any HubSpot object as part of the multi-threading recommendation.

## Structural fixes (also yours)
Off-deal engagement re-association · cross-deal duplicate consolidation · **Champion/EB contact labels (82/7)** — apply
these on the same per-deal approval. No separate RevOps bucket. **Company-association LABELS (End-Customer 78 / Reseller 3 /
Distributor 80) are NOT a rep-run fix** — the connector can't read association typeIds, so the **twice-daily batch**
(`audit_associations.py`) owns them: it auto-tags the obvious End-Customer via REST and flags only the ambiguous for a human.

## After the writes — verify & report what's outstanding (Phase 6)
Don't declare a deal done from the write call alone. **Re-read it from HubSpot** and confirm each approved change
landed with the intended value; **re-run the checks** to confirm the flag cleared and nothing new broke (a stage
bump raises the MEDDPICC bar; a line-item edit moves `hs_arr`). Then give the rep one closing ledger —
**✅ applied & verified · ⚠️ attempted-not-confirmed (retry / manual) · ⏭️ skipped · 🙋 needs your input ·
🔭 not yet deep-swept** — with a **before→after** flag count. Only say "0 outstanding for your
action" when ⚠️ and 🙋 are both clear.
