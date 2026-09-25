# MEDDPICC evidence verification (the manager's anti-gaming check)

The rep skill scores MEDDPICC by **content markers** (is the field substantive?). That catches *empty/thin*
fields — it does **not** catch a field that is plausibly written but **not backed by anything real**
("there is a champion; paper process goes to procurement" with no call, email, or note behind it). The
**manager skill closes that gap**: it verifies each populated MEDDPICC claim against the actual evidence —
**Fathom calls, email bodies, deal/contact notes, and public Slack** — and only credits qualification that the
record supports.

> **Principle 0 governs this entire check.** Never label a field "gamed/unsupported" without having actually
> searched the sources and found nothing. The *absence* of evidence must itself be cited ("searched Fathom
> (N meetings), 0 email bodies, Slack `#none`: no mention of procurement/PO"). A rep is innocent until the
> search comes back empty.

## When this runs
- **"Score a rep" / "drill into a rep" / "verify <rep>'s MEDDPICC":** run it on that rep's **forecasted deals**
  (`hs_manual_forecast_category` ∈ COMMIT / BEST_CASE) — those are what the number depends on, and where gaming
  matters. If the rep has few forecasted deals, extend to **Validate+ and top-weighted** deals.
- **Bounded:** cap at the rep's **COMMIT deals + top weighted** (≈ up to 8–10 deals). It is evidence-heavy —
  one rep at a time, never loop the whole team in one pass. **Log what you did not verify** (don't imply full coverage).
- The rep's own fast skill does NOT do this (it's a light run); this is the manager/accountability layer.

## What to verify (per deal, per populated MEDDPICC field)
For each deal in scope, take its **populated** MEDDPICC text (`identified_pain_v2`, `metrics_v2`,
`decision_criteria__cloned_`, `decision_process_v2`, `paper_process_v2`) and the named people/claims in it, then
look for corroboration across all four sources:

1. **Fathom calls** — `search_meetings` (company + stakeholder keywords, `recorded_by:"anyone"`, `max_pages:20`),
   `list_meetings` paged backward, `find_person` on each named stakeholder (exact spelling). Open
   `get_meeting_transcript` on the best matches. Is the claimed **pain / metric / decision-process / paper-process /
   named buyer** actually discussed? Cite `recording_id` + a verbatim quote.
2. **Email bodies** — recent `hs_email_html` (`hs_email_direction`: `EMAIL` outbound / `INCOMING_EMAIL` customer)
   on the deal + contacts. Does the correspondence reference the claim (a quoted price/metric, a procurement/PO
   thread, a named approver)? Cite the email (date + subject/snippet).
3. **Notes** — engagement notes on the deal and its contacts. Cite the note (date) where the claim appears.
4. **Public Slack** — `slack_search_public` for the deal/company channel (`#ciq-<company>`) and stakeholder
   mentions; for a POC, the channel often confirms success criteria / decision-process. Cite the permalink.
   (Public only by default — ask consent before any private search.)

## Verdict per field (and its effect on the score)
| Verdict | Definition | Effect |
|---|---|---|
| **VERIFIED** | A source corroborates the claim — cite it (`recording_id` / email / note / Slack permalink + quote). | Full qualification credit. |
| **PARTIAL** | Some support, but weaker/older than the field asserts (e.g. a metric mentioned once, months ago, never confirmed). | Credit at the evidenced depth, not the written depth; note the staleness. |
| **UNSUPPORTED** | Field is populated and *passes the content rubric*, but **no** call / email / note / Slack reference exists after a real search. | **Treated as thin** — no qualification credit; surfaced as **"qualification not evidenced"** (the gaming case). |
| **CONTRADICTED** | Evidence says the opposite (e.g. "procurement complete" but the latest call says legal hasn't started). | **Treated as a CRITICAL data-integrity flag** — the field misrepresents the deal. |

- **MEDDPICC depth for the manager's view uses the *evidenced* depth, not the written depth.** A field written at
  depth 8 but UNSUPPORTED counts as ~0 for qualification; a field CONTRADICTED counts as a critical flag. This is
  what makes "the manager skill catches gaming" true — a deal can't earn a clean MEDDPICC score on prose alone.
- Roll the per-field verdicts into a per-deal **`meddpicc_evidenced` vs `meddpicc_written`** read, and into the
  rep's coaching notes ("3 fields written, 1 verified, 1 unsupported, 1 contradicted").

## Reporting (Principle 0)
For every deal verified, show: the field, its written claim, the **verdict**, and the **cited evidence** (or the
cited *absence*: which sources were searched and what was found). Never assert "gamed" without the empty search on
record. Surface UNSUPPORTED/CONTRADICTED fields prominently for the manager — those are the coaching conversations.
List the deals **not** verified (out of the bounded set) so coverage is honest.
