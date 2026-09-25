# Corrections catalog — false positives to NOT repeat

Each line is a real mistake that produced bad reports. Honor the rule.

39. **A bare month WORD in `blockers` is NOT a hold date (parse_hold "may" bug; D-42, 2026-06-09).** Eleven brand-new cold
    "<partner> - RLC Partner Activation" deals all carried the boilerplate blocker "Price sensitivity - partner **may** have
    existing RHEL/SUSE contracts...". `parse_hold` read the English word "may" as month May -> a false 2027-05-01 hold that
    **suppressed dark / stalled / stale-next-step** on all 11, so never-contacted deals scored clean and "on hold" (Ani Fox,
    score 88). **Fix:** a month NAME only counts as a hold-until date when it carries a day/year ("May 2027", "Sept 15") OR a
    hold cue sits just before it ("paused until March", "revisit in September"); bare "may"/"march"/"august" are ordinary
    words. Golden-tested in `tests/test_rules.py`. (`lib/ciq_rules.py` `parse_hold` + `_HOLD_CUE`.) NOTE: the separate
    score-policy concern - that padding the open book with flagless new deals lifts Cleanliness via the `cap` - remains
    GATED/deferred pending review (ROLLOUT_FEEDBACK_DAY1 item 7c).

38. **⛔ NEVER include, flag, or close a CLOSED deal — the worst live failure (D-39, 2026-06-09).** A rep ran
    `/ciq-deal-hygiene` through his connector. The run pulled deals **without honoring `hs_is_closed=false`**, so two of his
    already-**Closed-Won** deals — Lockheed Martin Renewal 2026 ($52K, `22678916921`) and NREL Maris' Ascender ($44K,
    `42446349476`) — were listed as **"overdue"** (their close dates were in the past) and offered up as cleanup. On the rep's
    "close lost on all of these," the connector set **two won deals to Closed Lost**; trying to undo it, it could only strand
    them in Pending Approval (open, won-status erased, NREL's close date blanked). **Three compounding mistakes to never
    repeat:** (a) a closed deal entered scope at all (drop every `hs_is_closed=true` row at pull time); (b) a **past close date
    was read as "overdue → close it"** instead of "update the date on the OPEN deal" (golden rule 7); (c) the skill **executed a
    close-lost / stage change** — it must NEVER close, lose, win, reopen, or re-stage a deal into/out of a closed stage. Closing
    a deal is the rep's deliberate decision **in the HubSpot UI** (where pipeline approval / closed-edit rules apply; the API
    path bypasses them). Reducing at-risk is done by working/advancing real deals and fixing data — **never by writing deals
    off.** Codified: `SKILL.md` golden rule 12 + Step 1 hard-drop + Step 4 allowlist; `checks.md` execution guard + close-date
    note; `fix_playbook.md` stage/close-date guards. Incident: `INCIDENT_2026-06-09_connector_closed_won_edits.md`.

1. **Staleness from the wrong field.** Never measure staleness from `notes_last_updated`/`hs_lastmodifieddate`
   (they move when the rep edits a field). Use `notes_last_contacted` across the deal + contacts + End-Customer
   company. A refreshed Next Step does NOT make a deal "fresh." (Siemens Healthineers: edited 7d ago, customer
   not contacted in 57d — was missed.)

2. **Populated ≠ fresh (Next Step).** A populated Next Step can be months stale — read its most recent dated
   entry and flag >1 week.

3. **Champion/EB emptiness is NOT a qualification gap — and labeling them is the rep's job.**
   `champion_v2`/`economic_buyer_v2` are calculated from contact LABELS; empty means the label isn't applied.
   Only the rep knows who they are: identify them from transcripts/notes/email bodies, associate the contact
   to the deal, then apply the Champion (82)/EB (7) label. Still judge *qualification* on the MEDDPICC **text**
   (the buyer is often named in `decision_process_v2` even when the label is empty) — empty label ≠ unqualified.

4. **`amount` is unreliable.** Line items + `net_new_arr` are the source of truth; never trust `amount`.
   When `amount` and line items disagree, fix the line items.

5. **KRW/JPY/EUR ARR is not a discrepancy.** `hs_arr` (deal currency) vs `net_new_arr` (USD) legitimately
   differ by the FX rate. Don't flag it. Use `amount_in_home_currency` for USD.

6. **$0 ARR is often correct.** Professional-Services / Service / Product line items, POC deals, and embedded /
   OEM deals are legitimately $0 ARR. Only flag a true `subscription` line missing its billing frequency.

7. **"Close date in the past" ≠ "overdue/at risk."** It's a forecast date that slipped → "needs updating."
   Risk is judged by stage + engagement, not the close date.

8. **Do NOT flag `closedate > term_start`.** Co-term and expansion deals legitimately start the term before
   the deal closes (this fired on ~40% of deals — pure noise).

9. **Don't over-flag naming.** Clear names ("Airbus - Fuzzball") are fine. Only flag genuinely-unusable names
   (`[reseller]`, `test`, `TBD`, too short). Do not require a year or a strict 4-part convention.

10. **Owner names are always live.** Never invent or reuse an owner name; resolve it. Rose Stein shows as
    "Rose Samaniego" — address her as Rose Stein.

11. **Korean `MM.DD` (no year) / Japanese content is not "missing/undated as a gap."** Counts as populated;
    don't guess a date or flag it empty.

12. **Stage probabilities are live.** Always read `hs_deal_stage_probability`; never hardcode.

13. **Fathom retention is unlimited.** Never say "no coverage" from a shallow search — paginate `list_meetings`
    backward and use `find_person` (exact spelling) before concluding a meeting doesn't exist.

14. **Documented customer blocker (budget/spend freeze) downgrades a no-contact flag** (to WARNING, never below),
    with the blocker surfaced — don't penalize a rep for a freeze they've documented.

15. **Deals < 7 days old** never get a CRITICAL.

16. **Rep-run fixes: no separate RevOps bucket in the report.** Off-deal engagement re-association, cross-deal dedup, AND
    **Champion/EB contact labeling (82/7)** are rep actions applied in the run — don't carve out a "RevOps will handle this"
    section for those. **EXCEPTION — company-association LABELS** (End-Customer 78 / Reseller 3 / Distributor 80): the
    connector can't read association typeIds, so the **twice-daily batch** owns them (auto-tags the obvious End-Customer via
    REST, flags only the ambiguous). Don't chase company labels in the rep run. (D-36)

When a rep disputes a flag: don't defend it, accept the correction, and **append a structured feedback item to the deal's
`hygiene_feedback` property** (interim path — reps can't write the `Hygiene Run` object; see `fix_playbook.md` → Feedback).
Each item: `feedback_type`, verbatim skill-output + rep-correction, `check`, `evidence`, `status=new`. RevOps parses
`hygiene_feedback` across deals; a skill-improvement agent triages them into proposed entries here — **verified against
ground truth + human-confirmed** before they ship (a rep can be wrong too — Principle 0). The rep never fills a form.

---

## Live-QA findings (David Horn, 2026-06-03)

17. **Company-record sweep is mandatory (the Pfizer miss).** Account-dark must use the End-Customer **company** record's
    `notes_last_contacted`, not just the deal + its contacts. Pfizer was flagged "dark 99d" while the *company* record showed
    **May 18** (16 days). Skipping the company sweep = a false CRITICAL. (D003)
    *Live verification (2026-06-03): the skipped company-sweep + domain-match produced **5 of 7 false dark flags** across
    David Horn's book (Pfizer, Genentech, CZ Biohub, Airbus, DRI) — only Guardant (51d) and Cambridge/Drexel (70d) were genuinely stale.*
18. **Domain-matched contacts count (Petros Zolotas).** A contact on the End-Customer domain (`@pfizer.com`) is deal-relevant
    for staleness **even if not associated** to the deal — include in `true_last_contact` and surface to associate. (D005)
19. **Line items must be pulled (the skipped Pull B).** No Dimension-1/ARR flags fired in v1/v2 because line items were never
    pulled. Real misses: **ASU Fuzzball** subscription `hs_arr=$0` / `rbf=null` (deal amount $75k), **Airbus** $250k line-vs-deal
    ARR gap, **Genentech** term already expired. Pull B is mandatory before any D1 check. (D006)
20. **Never assert event dates from training data (Airbus ISC).** The report stated ISC as May; it was **June 18**. Take event
    dates only from Next Step / email / transcript / a HubSpot field, else "date unconfirmed." (D007)
21. **Search Slack for POC channels (Fluid Numerics).** A live POC channel `#ciq-fluidnumerics` existed; the skill didn't check.
    For Validate+ / active-POC deals, search for a deal/company-named channel before flagging stale. (D008)
22. **Off-system engagement looks dark (DRI in-person, Pfizer email).** Unlogged in-person meetings + emails not logged to HubSpot
    make deals appear darker than they are. Before finalizing a dark flag, ask the rep about unlogged in-person meetings/calls. (D002/D009)
23. **No HTML review artifacts (D011).** An interactive `hygiene-review.html` failed twice in the rep's environment. Deliver review
    in chat only (numbered list / fill-in template) — never an HTML/clickable artifact. Output format is otherwise flexible.
24. **Currency line-item gaps are real (UTAS Ascender, 58064724230).** Deal ARR $37,549 vs line items $52,500 on an AUD-quoted
    deal — the amount↔line-items check catches it; confirm the AUD quote/conversion before flagging final. (Live verification 2026-06-03.)

---

## Live-QA findings (Dave Dickerson, 2026-06-05 — Fathom `HGbUTx1F`)

25. **Future-dated customer cadence is NOT a gap (DD-3, the Sony/Derek miss).** When the customer set the cadence
    ("reach out in July/August," "come back in 3 months") and it's in the Next Step / transcript, the deal is
    **on-cadence until that date** — do not flag account-dark or stalled. "Nothing logged" ≠ a problem when there's
    nothing to log yet. Surface "on hold per customer until <date>"; only flag once that date passes with no contact.
26. **Order by soonest close date first (DD-1).** Default the review to the deals **closing soonest**, not by weighted
    value — that's the rep's working order. Forecast-mover weighting is the secondary sort within a close window.
27. **Skip freshly-updated deals (DD-2).** A deal whose Next Step was updated within the last **5 days** doesn't need
    re-review — note "recently updated, skipped" and move on; don't spend the run re-analyzing it.
28. **Light run by default; deep-sweep on request (DD-5).** Do NOT auto-pull Fathom/email for every deal (slow, big job).
    Default to HubSpot fields; offer "say the word and I'll deep-sweep a specific deal." Deep MEDDPICC evidence
    verification across a book is the **manager** skill's job.
29. **`blockers` is its own property (DD-7).** Blockers go in the dedicated open-text `blockers` deal property (set it to
    the blocker or "none" on every update), not buried in Next Step — so they're explicit and searchable.
30. **Content-marker MEDDPICC can be gamed (DD — Citrix hypothetical).** A populated-but-false field ("there's a champion;
    goes to procurement") passes the content rubric. The **rep light run cannot catch this**; the **manager skill** does,
    by verifying each claim against Fathom/email/notes/Slack (`meddpicc_verification.md`). Don't claim the rep run detects gaming.
31. **"All deals" pulls other pipelines (DD-8).** The skill is Sales-pipeline-only by default; if the rep says "all my
    deals," that also pulls Renewal/Alt — confirm scope before scoring those (the model is tuned for Sales).
32. **Partner/channel deals read in context (DD-11).** Reps working through partners can't always control cadence or see
    customer-side activity; note this caveat — the score reflects record completeness, not effort.
33. **Reps can't write the `Hygiene Run` object (deployment reality).** The browser connector can't create custom-object
    records, so rep scores/trend are written by the **twice-daily server-side batch**; the rep skill stamps deal-level
    `hygiene_score`/`blockers` instead. Reps deploy via a **Co-Work daily job** (DD-10).

---

## Scoring-engine fix (2026-06-06)

34. **Next-Step staleness must use the field's last-EDIT time, NOT a date scraped from the text (the "frozen scores" bug).**
    The batch scored Next-Step staleness by regex-parsing a date out of `hs_next_step` free text. That was unreliable both
    ways: it ignored the `M/D` (`6/5`) and `YYMMDD` (`240129`) formats reps actually use — so (a) a rep updating "6/5 - JF
    - …" got **no credit** (flag never cleared → score never moved), and (b) genuinely-ancient next steps with no parseable
    date went **unflagged** (e.g., one last edited 859d ago showed no flag). It also latched onto stale dates buried in
    appended history. **Fix:** staleness = days since `hs_next_step`'s most-recent property-history version (>7d WARNING,
    >30d CRITICAL); empty text → WARNING. Verified: re-scoring moved 13/17 reps (James +4 as his recent edits finally
    counted; Koji/Kelly/Scott down as their format-missed stale steps surfaced). The in-text date is display-only now.
    `hs_lastmodifieddate` is never used for this (batch/AI/rollups bump it). Applied to `score_all_reps.py` + `recompute_scores.py`.

36. **Reseller/distributor/partner activity must NOT clear an end-customer dark flag (cross-deal pollution).**
    A reseller/distributor (assoc typeId Reseller 3 / Distributor 80 / Technology Partner 9 / Cloud Marketplace 181)
    sits on *many* deals, and a contact's `notes_last_contacted` is context-free (their latest activity about *any*
    deal). Counting partner-contact activity in the staleness/`true_last_contact` sweep makes every deal that partner
    touches look engaged — silently bypassing the **dark** flag while the real end customer is silent. **Rules:**
    (a) resolve the End-Customer company via typeId **78** > Primary **5** > first **non-partner** company — never a
    reseller/distributor/partner; (b) the contact sweep counts only **End-Customer-domain** contacts (a contact whose
    email domain == the End-Customer company domain), excluding partner-domain contacts; direct deals (no partner
    associated) keep counting all non-generic contacts. (Stalled is pure stage-time and is unaffected — only **dark**
    was being bypassed.) Channel-only deals (no end-customer contact) fall back to deal/company `notes_last_contacted`
    and may flag dark — surface the partner-channel caveat (see #32), don't let a partner email mask it. Validated
    2026-06-06: 54 open deals carry a partner association; the fix re-flagged 1 falsely-cleared deal, 0 false changes.
    Applied in `score_all_reps.py` (`assoc_end_customer` fallback + contact-sweep domain filter) + `recompute_scores.py`.

37. **A next-step "refresh" must be a MATERIAL edit, and quality is judged separately (anti-gaming; refines #34).**
    #34 moved staleness to the field's last-edit timestamp (fixing the frozen-scores bug) — but a bare edit-timestamp is
    gameable: adding a comma re-stamps `hs_next_step` and would both clear "stale next-step" AND count as Cadence "worked."
    **Fix (deterministic, every deal):** compare consecutive `hs_next_step` property-history versions and ignore
    whitespace/punctuation/case-only diffs — freshness = days since the most recent *material* change; the SAME guard gates
    the Cadence "worked" signal (`_material_ts` / `_material_in_window` in `score_all_reps.py` + `recompute_scores.py`).
    **Content quality is a separate LLM check:** the manager run (and the engagement resolver) judges whether the next step
    is a specific, forward-looking action (concrete action + owner/date) vs vague filler ("follow up" / "touch base" / a
    recycled line) → a **"thin next-step"** flag, the direct analog to thin MEDDPICC, verified against call/email content.
    The rep light run can't catch a well-worded-but-false next step; the manager does. Validated 2026-06-06 (unit tests:
    comma/whitespace/case-only edits correctly fall back to the prior material edit; live re-run moved 1 deal, right direction).

35. **Renewal/expansion line-item↔ARR gaps are expected, not a flag (NASA-Johnson).** A deal with `renewal__expansion="true"`
    or `dealtype` containing "expansion" legitimately has line-item TCV > `net_new_arr` — the line items carry the renewed
    base + expansion while `net_new_arr` is the NEW portion only. Do NOT raise the line-item/ARR-gap flag for these.
    (There may still be a genuine calc issue to reconcile against the expiring contract(s) being replaced — but that's a
    deeper check, not the naive |line_sum − net_new_arr| flag.) Applied in `score_all_reps.py` line-item check.
