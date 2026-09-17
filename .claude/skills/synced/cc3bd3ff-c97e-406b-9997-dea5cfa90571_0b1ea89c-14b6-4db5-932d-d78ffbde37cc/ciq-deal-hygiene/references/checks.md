# Hygiene Checks — corrected logic, thresholds, suppressions, owner

Every flagged item is **yours** to fix and apply — one rep workstream, no separate "RevOps" bucket in the report. (The Owner column below reads "you" throughout.)
Severity = CRITICAL / WARNING / INFO. Apply the suppression rules throughout. Cite the source of every flag.

---

## Dimension 1 — HubSpot data integrity

| Check | Condition | Sev | Owner |
|---|---|---|---|
| dealtype null | `dealtype` empty | WARNING | you |
| Misrouted dealtype | `existingbusiness` in Sales pipeline, or `Retraction` (invalid value) | CRITICAL | you |
| New-Biz ARR variance | `dealtype=newbusiness`, USD deal, `hs_arr` vs `net_new_arr` differ >5% | WARNING | you |
| Expansion ARR error | `dealtype=Expansion` and `net_new_arr > hs_arr` | CRITICAL | you |
| Amount ↔ line items | `amount`/`hs_tcv` ratio >2× → CRITICAL; material USD gap (> max($1k,10%)) → WARNING. `amount` is unreliable — fix the **line items**, not the amount. | CRITICAL/WARNING | you |
| Amount, no line items | `amount`>0 but `hs_tcv` null and no line items | CRITICAL | you |
| $0-ARR subscription | a `subscription` line item missing `recurringbillingfrequency` → hs_arr=$0. **Exempt: POC, embedded, Professional-Services/Service/Product lines** (legitimately $0). | WARNING | you |
| No line items at stage | Qualified+ with zero line items | WARNING | you |
| Term inversion | `term_start > term_end` | CRITICAL | you |
| Term length mismatch | span(`term_start`→`term_end`) vs `length_of_term__months_` differ >1mo, **positive spans only** (negative span = inversion above) | WARNING | you |
| **Stage<->close-date coherence** (D-40) | open deal with a **past close date -> WARNING** (re-date it; age = days overdue); **early-stage** (Discovery/Qualified) deal **closing <=30d out -> CRITICAL** (can't traverse the remaining stages that fast - usually a sandbagged/default date). Validate+ are exempt from the imminent-CRITICAL (closing soon is healthy there); the overdue WARNING applies to any open deal. **Won-stage deals (`93217107` / `1162796937`) are dropped at fresh-read and never reach this check** (they are terminal/out-of-scope, despite `hs_is_closed=false`). **Joins the forecast-threat set** (counts toward forecast-at-risk). **Fix = re-date the OPEN deal or advance a stage forward among OPEN stages; NEVER close it lost (golden rule 12).** | CRITICAL/WARNING | you |
| Currency null | `deal_currency_code` empty on a deal with amount>0 | WARNING | you |
| Placeholder deal name | name is a placeholder/unusable (`[reseller]`, `test`, `TBD`, `untitled`, < 6 chars). **Do NOT** flag clear names for lacking a year/4-part convention. | INFO | you |
| End Customer (78) missing | no company associated, or company associated without the End Customer label | CRITICAL/WARNING | you (associate the company + apply the End Customer label) |
| reseller_deal ↔ partner | `reseller_deal=true` but no Reseller(3)/Distributor(80) company; or partner labeled but flag not true | CRITICAL/WARNING | you (apply the Reseller/Distributor label / set the flag) |

> **Do NOT flag `closedate > term_start`.** Co-term and expansion deals legitimately begin the term before
> the deal closes — this fired on ~40% of deals and is normal. (corrections.md)

> **⛔ A past close date is NEVER grounds to close a deal (golden rule 12 / D-39).** "Close date in past" is a coherence WARNING (D-40) —
> *update the date on the OPEN deal.* It must never become "overdue → mark Closed Lost." Writing a deal off is a
> forecasting decision the rep makes manually in HubSpot, not a hygiene fix.

---

## Dimension 2 — Your sales motion

| Check | Condition | Sev | Owner |
|---|---|---|---|
| Next Step empty | `hs_next_step` blank | WARNING | you |
| **Next Step stale** | the **`hs_next_step` field's last *material* edit** (property history) is >7d old → WARNING; >30d → CRITICAL. **Authoritative signal = when the field was meaningfully updated, NOT a date scraped from the text** (text dates vary — `6/5`, `MM.DD.YY`, `YYMMDD` — and scraping both misses recent edits and catches buried old dates). **Only a material edit refreshes it** — a whitespace/punctuation-only change (e.g. adding a comma) does NOT count: the batch diffs property-history versions and ignores trivial edits, and the same guard applies to the Cadence "worked" signal (anti-gaming). The **manager run** additionally judges next-step **quality** — a specific, forward-looking action vs vague filler ("follow up"/"touch base"/a recycled line) — a "thin next-step," verified against call/email content like MEDDPICC. (Thin/read-only connector that can't see field history: treat a just-edited step as fresh and use the in-text date only as a display aid.) | WARNING/CRITICAL | you |
| MEDDPICC depth | each MEDDPICC **text** field below its stage threshold (see `meddpicc_rubric.md`). Score on substance, not the Champion/EB checkbox. | CRITICAL if required≥6 & empty, else WARNING | you |
| Stakeholder breadth | single-threaded: fewer contacts than the stage needs (Qualified+ : <2, Propose+ : <3). Discovery exempt. | WARNING | you |
| Outbound cadence | rep-outbound emails in last 30d below the stage minimum (Qualified 1, Validate/Propose 2). *Proxy: emails only.* | WARNING | you |
| Post-meeting follow-up | a Fathom-recorded meeting in last 60d with no rep-outbound email within 5 days after it | WARNING | you |
| Self-set escalation lapsed | Next Step says "escalate / if no response by…" and the entry is >14d old (trigger not acted on) | WARNING | you |
| Stage-advancement ready | MEDDPICC depth already meets the **next** stage's bar (and line items exist) → consider advancing (forecast may be understated) | INFO | you |
| Champion / EB not identified + labeled | `champion_v2` (Qualified+) or `economic_buyer_v2` (Validate+) empty. **This is yours:** name who they are from your transcripts / notes / email bodies, make sure that contact is associated to the deal, then apply the Champion (82) / EB (7) label — see `fix_playbook.md`. (Empty label ≠ unqualified; judge depth on MEDDPICC text.) | WARNING | **you** |

---

## Dimension 3 — Customer engagement

| Check | Condition | Sev | Owner |
|---|---|---|---|
| **Account dark** | no contact across the deal **and** its contacts **and** the End-Customer company: >30d → WARNING, >60d → CRITICAL. Measured by `notes_last_contacted` (last contact), NOT last edit. | WARNING/CRITICAL | you |
| Masked activity | deal edited ≤14d ago but the customer not contacted >30d (internal busywork, not customer-facing) | WARNING | you |
| Emailing into silence | ≥3 rep-outbound emails in 30d with 0 customer replies | WARNING | you |
| Stall/risk language | stall phrases in recent emails / Next Step / transcripts ("budget freeze," "pushed," "next quarter," "reorg," "on hold," "deprioritized," "no budget," "acquired," "layoff," "back burner"…) | WARNING | you |
| Possible unmet commitment | rep promised follow-through ("will send," "by EOW/Friday") >10d ago with no customer reply since | WARNING | you |
| Off-deal activity | the account was engaged ≤30d ago but it isn't logged to the deal | WARNING | you (associate the activity/contact to the deal) |
| Documented blocker | a customer-imposed budget/spend freeze is documented → downgrade the no-contact flag to WARNING (never below); surface the blocker, don't penalize | — | you |

---

## Account intelligence
- **Cross-deal overlap** — 2+ open deals at the same End Customer → confirm they're distinct, or consolidate the duplicate. (Yours.)
- **Channel-deal card scoping** — each deal card in your report is scoped to its own named end customer. If a card shows a **⚠ Channel deal — verify scope** note, it means the engagement resolver has not yet run for this deal; the recommendation may reference activity from a sibling deal sharing the same partner but a different end customer — read it critically and keep your actions scoped to this deal's end customer only.

---

## Evidence reconciliation & scheduling
Run after the evidence sweep (`evidence_extraction.md`) — compare the CRM against what was actually said, and check forward motion.

| Check | Condition | Sev | Owner |
|---|---|---|---|
| CRM contradicted by call/email | a deal field (close date, competition, champion, decision process, pricing) disagrees with a cited transcript/email | WARNING | you |
| Logging gap (under-logged) | a Fathom call / email exists that isn't reflected in `notes_last_contacted` → reconcile; do **NOT** flag account-dark. **Extended (D3):** a note body describes an in-person meeting or call that was never logged as a Meeting engagement → recommend creating the Meeting (see `fix_playbook.md` § "Note describes a meeting that was never logged"). Surface the `log_meeting` recommendation from the report; do NOT auto-credit the note for dark-suppression in scoring. | INFO | you |
| No upcoming meeting | active deal (Validate+) with no scheduled future meeting AND no Next Step referencing a booked one → momentum risk (Discovery/Qualified = INFO) | WARNING | you |
| Upcoming meeting (context) | a future meeting IS booked → surface it ("next: \<date\> w/ \<contact\>"), source the Next Step from it, treat the account as in-motion (not dark) | — | you |
| Domain-matched off-deal contact | a contact on the End-Customer **domain** has activity more recent than the deal's associated contacts → include in `true_last`; surface to **associate to the deal** (D005) | WARNING | you |
| Cross-functional CIQ activity | PS/CSM/eng or sibling-deal contacts active on the account → surface as engagement context, don't flag dark (D010) | INFO | you |

---

## Execution guards (rigor — post-live-QA)
- **⛔ Won/closed deals & closed-stage moves are OUT OF SCOPE (golden rule 12 / D-39).** Drop at pull time every deal that is **either** `hs_is_closed=true` **or** in a Won stage (`93217107` Sales Won / `1162796937` Alt Won — note: HubSpot reports `hs_is_closed=false` on these, but they are terminal wins awaiting finance booking and are never open rep work) — never analyze, flag, score, or write to a Won or Closed Won/Lost deal. **Never** set a deal to Closed Lost / Closed Won or reopen one, even if the rep asks — that's a forecasting decision they make manually in the HubSpot UI (where pipeline approval / closed-edit rules apply; the connector's API path bypasses them). Stage *advancement* is allowed only **forward among OPEN stages, never to/at/past Won**, never into a closed stage, never on an already-closed or Won deal. *(Live incident: a `/ciq-deal-hygiene` run closed-lost two of the rep's own Closed-Won deals — corrections.md #38.)*
- **Per-deal completeness (anti-skip).** Before judging a deal you MUST have actually fetched: the End-Customer **company** record's `notes_last_contacted`; its **line items**; and **domain-matched contacts**. Record per-deal coverage in the run-record (`run_record.md`). Missing any → not done; go fetch it. *(Pull D company-sweep and Pull B line items were both skipped in the live test.)*
- **Event-date guard (D007).** Never assert event/conference/calendar dates from training data — use Next Step / email / transcript / a HubSpot field, else "date unconfirmed."
- **Unlogged in-person (D009).** Before finalizing an account-dark flag, ask the rep about unlogged in-person meetings/calls — invisible to the connectors.
- **Chat-only (D011).** Deliver in chat; never build HTML / artifacts / files / debug logs / versioned reports.
- **Capture blockers explicitly (DD-7) — ADVISORY, not scored.** On every deal you update, set the dedicated open-text
  **`blockers`** property to the current blocker (what it is) or **"none"** — never bury a blocker in the Next Step. Surface
  a deal where a blocker is evident (stall language, a known dependency in notes/transcripts) but `blockers` is empty →
  nudge the rep to populate it. **This does NOT lower the deal's score** — the batch never penalizes an empty `blockers`
  field; the field only matters as a *hold-until date* that *suppresses* dark/stalled flags. Don't count "blocker uncaptured"
  in `weighted_open`.

---

## Suppression rules (always apply)
- **Future-dated customer cadence → not dark/stalled (DD-3).** If the Next Step / a transcript / an email shows the customer
  set the cadence ("reach out in July," "come back in Q3," "they said next quarter"), the deal is **on-cadence until that
  date** — suppress account-dark and stalled, surface "on hold per customer until <date>," and only flag once the date
  passes with no contact. A booked future meeting is the same (in-motion, not dark). "Nothing logged" ≠ a gap when there's
  nothing to log yet.
- Deals < 7 days old → never CRITICAL.
- Discovery exempt from MEDDPICC-depth flags (flag only Identified Pain completely empty) and from stakeholder-breadth.
- `reseller_deal` null → only an issue if a Reseller/Distributor company is actually attached.
- POC / embedded / Professional-Services / Service / Product line items → legitimately $0 ARR; never flag.
- KRW/JPY/EUR `hs_arr` vs USD `net_new_arr` → never flag as variance (FX, not a discrepancy).
- `close date in the past` on an open deal -> the **close-coherence WARNING** (D-40): re-date the OPEN deal (counts toward forecast-at-risk); still NEVER "overdue -> close it lost" (golden rule 12).
- `closedate > term_start` → not flagged (normal for co-term/expansion).
- Korean `MM.DD` / Japanese Next Step or MEDDPICC content → counts as populated; don't flag empty/undated as a gap.

---

## Output — surface these signals (format is FLEXIBLE, not fixed)
Present in chat only (no HTML/artifacts). The **layout is open to iterate with the rep — do not lock a template.** Convey at least:
- the count of each issue type below, and the deals that move the forecast first (highest weighted value);
- per deal: cited flags + a **proposed** drafted update (Next Step, MEDDPICC, champion/EB contact to label, competition, close-date, line-item/ARR), marked *not yet written*;
- the structural fixes that are **yours** — off-deal re-association · cross-deal dedup · **Champion/EB contact labels (82/7)** (no separate RevOps bucket). **Company-association labels (EC 78 / Reseller 3 / Distributor 80) are batch-handled** (REST reads the typeIds the connector can't), not a rep-run action;
- which deals only got the light CRM pass (offer to deep-sweep).

Issue types (for the rep's counts — a reference list, **NOT** a mandated table/format):
Stage stalled · Account dark 30d+ · Next Step stale/empty · Close/stage coherence (past, or early-stage + imminent) · Line items/ARR · Term dates ·
MEDDPICC thin · Emailing into silence · Low outbound cadence · No post-mtg follow-up · Unmet commitment ·
Stall language · Escalation lapsed · Single-threaded · Champion/EB to identify+label · Domain-matched off-deal contact ·
CRM contradicted by call · No next meeting · Logging gap · Can advance stage · Term length mismatch · Placeholder name · Blocker uncaptured _(advisory — not scored)_.
