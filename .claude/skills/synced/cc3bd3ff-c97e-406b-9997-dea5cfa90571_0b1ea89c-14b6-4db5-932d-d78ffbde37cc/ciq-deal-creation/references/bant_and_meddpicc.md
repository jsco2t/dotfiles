# BANT Gate & MEDDPICC Fields

## The BANT gate (hard block on deal creation)
All four must be confirmed before the summary. This is not negotiable and does not relax on rep insistence, a stated dollar amount, or "I'll fill the rest in myself." When a criterion is missing, respond: `❌ Cannot create deal — missing [criterion]. This isn't a qualified opportunity yet — qualify it (discovery call) and come back.` List exactly what's missing.

| Criterion | ✅ Accept | ❌ Block |
|---|---|---|
| **Budget** | "$X allocated" · "budget identified, approval in progress" · "approved by finance" | "don't know yet" · "need to find out" · "they're exploring" |
| **Authority** | decision-maker with **name AND title** ("Mark Tugwell, Sr Mgr IT") · "EB is Sarah Johnson, CFO" | "still figuring out" · "someone in IT" · first-name-only or title-only |
| **Need** | specific pain **+ product match** ("replacing AAP with Ascender Pro for SLA + auto-scaling licensing") | "interested in learning more" · "just exploring" · no product named |
| **Timeline** | decision/implementation date, quarter, or compelling event ("AAP expires Sept 9 2026") | "no rush" · "whenever" · "don't know" |

Never create from a bare website form, a pricing-only request, or a generic "tell me more" contact.

**From a transcript:** extract BANT silently. If complete → proceed. If not → show what you found, name what's missing, and STOP at the gate (don't proceed to summary).

**Asking BANT without a transcript:** ask the four in one batched prompt. Budget is often a value/range (free text), but you can triage authority-of-budget with a tappable set — **"Allocated" / "Identified, approval pending" / "Not confirmed yet"** — where "Not confirmed yet" BLOCKS. Authority is a name+title (free text). Need is pain + product (product can be tappable from the catalog; pain is free text). Timeline can be tappable (a quarter or "specific date" → then typed). See SKILL "Asking questions."

## MEDDPICC fields (internal names)
| Component | Property |
|---|---|
| Metrics | `metrics_v2` |
| Economic Buyer | `economic_buyer_v2` (editable string; also fills from EB label 7) |
| Decision Criteria | `decision_criteria__cloned_` |
| Decision Process | `decision_process_v2` |
| Paper Process | `paper_process_v2` |
| Identified Pain | `identified_pain_v2` |
| Champion | `champion_v2` (editable string; also fills from Champion label 82) |
| Competition | `competition` (enum — see ciq_reference) |

**Rules:**
- **Append-only:** `identified_pain_v2`, `decision_criteria__cloned_`, `decision_process_v2`, `paper_process_v2`, `metrics_v2`, and `hs_next_step` are never overwritten. Read current → append/summarize → write back. Show current-vs-new before writing.
- **MEDDPICC fields contain HTML** — strip tags before analysis or display.
- **At Discovery (creation)**, required MEDDPICC = Identified Pain, Competition, Metrics (best-effort), and Next Step. Decision Criteria / Decision Process / Paper Process are optional at Discovery and filled as the deal advances.

## Next Step format
`MM.DD.YY [Rep Initials] - [action]` — e.g. `07.01.26 AV - Demo scheduled early next week; customer confirming day/time this week.` When updating, add the new dated entry **above** the existing text (reverse-chronological), never replacing it.
