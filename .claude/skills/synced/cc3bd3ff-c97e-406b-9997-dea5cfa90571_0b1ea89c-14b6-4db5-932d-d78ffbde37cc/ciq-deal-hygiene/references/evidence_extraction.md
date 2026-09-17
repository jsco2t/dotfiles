# Evidence extraction — turn conversations into proposed CRM updates

Evidence-first means: read the transcripts / emails / Slack **before** judging the CRM, extract the ground
truth, and map each fact to the HubSpot field it should populate — as a **proposed** update the rep approves.
Principle 0 applies to every extracted value.

## Citation & integrity rules (non-negotiable)
- Every extracted fact **cites its source**: Fathom `recording_id` + a verbatim quote, the email id (subject + date), or a Slack permalink.
- **Never invent a quote, name, date, or number.** If it isn't in the evidence, it's *unverified* — say so; do not pre-fill it.
- **Exact-name matching only** (the Harald-not-Harry rule): confirm spelling against HubSpot contacts / Fathom attendees before naming anyone.
- Pre-filled values are **proposals, never auto-writes** — the rep approves per deal (Phase 5).
- Evidence corroborates; it does not license an overwrite — **APPEND** to Next Step / MEDDPICC, never replace.
- No transcript found ≠ "no meeting": deep-pull first (unlimited retention). Only then record it as a coverage gap.
- **Domain relevance (D005):** a contact whose email domain matches the End-Customer company domain is deal-relevant for
  staleness **even if not associated** to the deal — include them in `true_last_contact` and surface them to associate.
  Exclude generic domains (gmail.com, outlook.com, yahoo.com…).
- **Event-date guard (D007):** never state an event / conference / calendar date from training data — take it only from the
  Next Step text, an email/transcript, or a HubSpot field; otherwise say "date unconfirmed." (Don't repeat the ISC May-vs-June miss.)

## What to extract → where it maps
| From the conversation | HubSpot field (proposed) | Notes |
|---|---|---|
| Who drives the decision / sells internally | Champion → contact→deal label **82** | name the exact contact; associate to the deal first |
| Who controls budget / signs | Economic Buyer → label **7** | distinct from champion; cite where identified |
| The business pain stated | `identified_pain_v2` (append) | quote the customer's own words |
| Quantified targets / success metrics | `metrics_v2` (append) | numbers, KPIs, timelines they named |
| How they'll decide / requirements | `decision_criteria__cloned_` (append) | must-haves, eval steps |
| Decision process / approvers | `decision_process_v2` (append) | stakeholders, sequence, committee/board |
| Procurement / legal / paperwork | `paper_process_v2` (append) | PO, MSA, security review, timing |
| Competitor named or incumbent | `competition` (enum — see `reference_data.md`) | valid enum values only |
| Timing language ("by Q3", "after budget") | `closedate` (propose realistic) | reconcile against current close date |
| Pricing / SKU / term discussed | line items (`recurringbillingfrequency`, price, qty, term) | propose the SKU/term actually agreed |
| Commitments ("I'll send…", "by Friday") | `hs_next_step` (append, dated) | becomes the concrete next action |
| Most recent real touch (call/email) | reconcile vs `notes_last_contacted` | distinguishes logging gap from dark account |

## Reconciliation classes (apply per field)
- **matches** — CRM agrees with the evidence → no action.
- **missing** — discussed but blank in HubSpot → propose the value from the evidence.
- **stale** — CRM superseded by something said since → propose the update (append).
- **contradicted** — CRM disagrees with what was said → surface both, propose the corrected value, flag for confirmation.
- **logging gap** — a real meeting/email exists but the activity wasn't logged → under-logged, **not** a dark account; do not flag account-dark.
- **unverified** — no source found → state it's unverified; do **not** pre-fill.

## Order of trust
Customer's own words (transcript) > the rep's contemporaneous email > Slack mention > a stale CRM field.
When evidence and CRM disagree, the **conversation is the ground truth** — but you still *propose*; the rep confirms.

## Output of this phase (feeds the per-deal cards)
For each priority deal, a compact ledger: `field → class (missing/stale/contradicted/logging-gap) → proposed value → source (recording_id/email)`.
Phase 4 renders this as approve/tweak/skip; Phase 5 writes the approved ones.
