# Reference data

## Portal & fiscal
- HubSpot portal **22461953**. FY26 = **Feb 1 2026 – Jan 31 2027** (Q1 Feb-Apr · Q2 May-Jul · Q3 Aug-Oct · Q4 Nov-Jan).
- **Excluded owners (NOT reps — skip in all hygiene reports & scoring):** Matthew Hayden (`237243408`, matt@ciq.com) — RevOps + a test deal.
- Pipelines: **Sales 45314112** (this skill) · Renewal 49231982 (only on request) · **Alt 793851464 — never**.

## Sales pipeline stages (pull live `hs_deal_stage_probability`; never hardcode probabilities)
93217102 Discovery · 93217103 Qualified · 93217104 Validate · 93217105 Propose & Negotiations ·
93217106 In Procurement · 1205882270 Pending Approval · 93217107 Won · 143973802 Closed Won · 93217108 Closed Lost.

## Property set to pull (Pull A)
Core: `dealname, dealstage, pipeline, dealtype, hubspot_owner_id, closedate, hs_createdate, hs_lastmodifieddate`
Term: `term_start, term_end, length_of_term__months_`
Financial: `amount, amount_in_home_currency, deal_currency_code, hs_tcv, hs_acv, hs_arr, net_new_arr, hs_deal_stage_probability`
Forecast/timing: `hs_manual_forecast_category, hs_forecast_probability, hs_projected_amount_in_home_currency, hs_v2_date_entered_current_stage, hs_v2_time_in_current_stage, quote_expiry_date`
MEDDPICC (text): `identified_pain_v2, metrics_v2, decision_criteria__cloned_, decision_process_v2, paper_process_v2, competition`
Calculated label fields (proxies): `champion_v2, economic_buyer_v2`
Status/activity: `hs_next_step, reseller_deal, renewal__expansion, notes_last_contacted, notes_last_updated, num_notes, num_contacted_notes`
Hygiene (write-back — `deal_hygiene` group): `hygiene_score` (number 0–100, this deal's own cleanliness), `last_hygiene_score_date` (date), `blockers` (open text — the blocker or "none"), `hygiene_feedback` (textarea — append-only JSON array of rep feedback items on the skill's output for this deal). The Layer-A batch stamps `hygiene_score`/`last_hygiene_score_date` 2×/day; the rep skill stamps them + `blockers` on the deals it fixes, and **appends to `hygiene_feedback`** when the rep disputes a flag (`fix_playbook.md`). (Score formula in `run_record.md`.)
Meetings/scheduling: meeting engagements with `hs_meeting_start_time` (+ `hs_meeting_outcome`). Upcoming = start ≥ today (forward motion); past + no outcome/recording = logging gap.

## Authoritative-field registry (which field to trust — this is where most mistakes come from)
| Signal | USE | Do NOT use |
|---|---|---|
| Deal value (forecast) | `net_new_arr` (USD, canonical) → then `net_new_arr × prob` weighted → `amount_in_home_currency` | `amount` (unreliable: sometimes TCV, sometimes annual), `arr` |
| USD money sums | `amount_in_home_currency` | raw `amount` (deal currency; KRW inflates ~1,430×) |
| ARR currency | `hs_arr` is in **deal currency**; `net_new_arr` is **USD** — don't compare cross-FX | — |
| Customer-contact recency / staleness | `notes_last_contacted` (deal + contacts + company) | `notes_last_updated`, `hs_lastmodifieddate` (move on edits) |
| Time in stage | `hs_v2_time_in_current_stage` / `hs_v2_date_entered_current_stage` | — |
| Qualification depth | MEDDPICC **text** fields | `champion_v2`/`economic_buyer_v2` emptiness (those are label-driven) |

## Stage stagnation thresholds (days in current stage) — recalibrated for long-cycle deals (2026-06-06)
Discovery 120 · Qualified 90 · Validate 75 · Propose & Negotiations 45 · In Procurement 30 · Pending Approval 21.
(Earlier values 60/60/45/30/30/21 over-flagged federal/long-cycle Discovery deals.)
Over the threshold = "stalled" (the deal is weighted at a probability it hasn't earned).

## Stage<->close-date coherence (D-40, live via `--use-close-coherence` in the batch)
Early-stage open deal (**Discovery** rank 1 / **Qualified** rank 2) with a close date **<=30 days out -> CRITICAL** (can't traverse the remaining stages that fast - usually a sandbagged/default close date). **Any open deal already past its close date -> WARNING** (age = days overdue). Validate+ (rank >=3) are **exempt from the imminent-CRITICAL** (closing soon is healthy there); the overdue WARNING applies to any open deal. **Won-stage deals (`93217107` Sales Won / `1162796937` Alt Won) are terminal/out-of-scope at fresh-read** — dropped before any check runs and never analyzed, flagged, or written, despite reporting `hs_is_closed=false` (PO received, awaiting finance booking). Joins the **forecast-threat set** and is a scored flag in the per-deal `hygiene_score`. Constants `CLOSE_COH_LOWRANK=2`, `CLOSE_COH_LOWRANK_DAYS=30` (`lib/ciq_rules.py` `close_coherence`).

## Closed-lost integrity window (manager-report only, D-42)
"Recently closed lost" = a Closed-Lost deal with `closedate` within **30 days** back (`CLOSE_LOST_WINDOW`). Powers the manager skill's write-off legibility / missing `closed_lost_reason` / same-company recreate checks (`is_recent_close_lost`, `recreate_candidates` in `lib/ciq_rules.py`). NEVER a rep-score input (the hygiene score sees only the OPEN book).

## Currency (USD conversion, refresh quarterly)
USD 1.00 · KRW ÷1,430 · JPY ÷151 · EUR ×1.05. Display non-USD as "$X USD (native)". Use `amount_in_home_currency` for sums.

## Association type IDs
Company→deal: End Customer **78** (required) · Reseller **3** · Distributor **80** · Primary 5 · Paying Entity 86.
Contact→deal: Champion **82** · Economic Buyer **7** · Billing Contact **85**. **The rep applies Champion/EB** after identifying the person from their evidence (associate the contact to the deal, then set the label). **Company-association labels (End Customer 78, Reseller 3, Distributor 80) are NOT a rep-run action** — the connector can't read association typeIds, so the **twice-daily batch** owns them (`audit_associations.py`: auto-tags the obvious End-Customer via REST, flags the ambiguous for a human). Don't set company-association labels in the rep run.

## Competition enum (valid values only)
Red Hat · CentOS · Oracle Linux · Alma Linux · Ubuntu · Suse · Self-Supported Rocky · Tux Care · Self Support · None · Rescale · HPE · ParallelWorks · NavOps by Altair.

## Names
Rose Stein displays as "Rose Samaniego" in HubSpot — address her as "Rose Stein."
Korean deals owner Ally/Tommy (81176068); Japanese owners Koji Matsushima (81491120), Yoshi Matsumoto (568562062) — their MEDDPICC/Next Step may be in Korean/Japanese (counts as populated).
