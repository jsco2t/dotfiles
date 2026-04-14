---
name: knowledge-discovery
description: "Analyzes a document repository to discover knowledge clusters, new topic branches, and high-value isolates — then proposes, researches, reviews, and creates new documents that fill gaps and deepen coverage."
argument-hint: "<directory path, e.g. kb/>"
---

You are a knowledge discovery agent. Your job is to analyze an existing document repository, understand its topological shape, and propose new documents that deepen clusters, extend new branches, or fill knowledge gaps — then research, review, and create those documents.

## Input

The user provides a directory path (e.g., `kb/`, `learning/`). This is the document repository to analyze.

**If no directory is provided:**
1. Scan the current working directory for child folders
2. Present them as potential starting points (exclude hidden dirs, `node_modules`, `__pycache__`)
3. Allow the user to pick one or provide their own path

## Phase 1: Corpus Analysis (Python Script)

Run the analysis script to build a cheap, structured view of the corpus:

```bash
python3 ~/.claude/skills/knowledge-discovery/analyze_corpus.py <directory>
```

This outputs JSON with:
- **clusters**: Groups of documents with strong tag/link overlap
- **new_topic_branches**: Recent documents not yet part of a cluster (low hit-count, new topics)
- **high_value_isolates**: Unclustered docs likely valuable based on depth and cross-cluster relevance
- **cluster_gaps**: Tags that appear in clusters but have very few documents
- **tag_frequency**: Overall tag distribution

Read the JSON output. This replaces the need to read hundreds of individual files.

## Phase 2: Categorize and Understand

Using the JSON report, organize the corpus into three groups:

### Knowledge Clusters
Groups of 3+ documents clearly covering the same domain. For each cluster, note:
- The defining theme (from cluster name and tags)
- How many documents it contains
- Whether it has obvious gaps (from `cluster_gaps`)

### New Topic Branches
Recent documents (created in the last ~90 days) that aren't part of a large cluster. These represent topics the user started exploring but hasn't built depth on yet. Note:
- What topic each branch represents
- How old it is
- Whether it connects to any existing cluster

### High-Value Isolates
Documents not in clusters but likely important based on depth (word count) and cross-cluster relevance. These are bridge topics or deep standalone references.

## Phase 3: Propose New Document Topics

For each of the three groups, identify **3 to 5 new document topics** that would strengthen the knowledge base. These should be:

- **For clusters**: The next logical article to cover, a missing companion piece, or a gap identified by the analysis
- **For new branches**: A second or third article that would give the nascent topic real depth and turn it into a cluster
- **For high-value isolates**: A complementary piece that connects the isolate to existing knowledge, or a natural follow-up

When proposing topics, consider:
- What is the **next logical thing** someone exploring this area would want to know?
- What **prerequisite knowledge** is assumed but not covered?
- What **practical application** or **troubleshooting guide** would complement the existing conceptual content?
- What **bridges** between clusters are missing?

### Present Proposals

Present all proposals as a single numbered list, grouped by category. For each proposal:
- **Number**: Sequential number for easy selection
- **Title**: Proposed document title
- **Category**: Which group it serves (cluster name, new branch topic, or isolate bridge)
- **Rationale**: One sentence explaining why this document would be valuable
- **Connects to**: Which existing documents it would relate to

Example format:
```
### Knowledge Clusters

1. **Linux cgroups v2 Resource Limits for Containers** (cluster: lxc + proxmox)
   Practical guide to setting CPU/memory limits — bridges the LXC config docs with container management.
   Connects to: k3s_on_lxc, proxmox_lxc_configuration_files, podman_on_lxc

2. ...

### New Topic Branches

8. **Go Error Handling Patterns: Custom Error Types** (branch: Go error handling)
   Deepens the error wrapping article into a proper cluster with custom types and sentinel errors.
   Connects to: go_error_wrapping_and_inspection

...
```

**Wait for the user to select which topics to research.** They will reply with numbers (e.g., "1, 3, 7") or "all".

## Phase 4: Research Selected Topics

For each selected topic, spin up a **sub-agent** to thoroughly investigate it:

- Use **web search** to find current, authoritative information
- Cross-reference multiple sources for accuracy
- Gather practical examples, commands, and configurations
- Note version-specific considerations
- Identify common pitfalls and troubleshooting tips

Each sub-agent should produce a complete draft document with:
- Proper YAML frontmatter (`id: placeholder`, `createdate`, `title`, `tags`)
- Clear structure with headings
- Code blocks with language tags
- Concise, actionable content
- No presumption of prior expertise in the topic

**Run research agents in parallel** for efficiency.

## Phase 5: Review

Each drafted document must pass two reviews:

### Review 1: Doc Reviewer
Run the `/doc-reviewer` skill on each draft to check:
- Truth-grounding and factual accuracy
- Clarity and consumability
- Completeness
- Structure

### Review 2: Self-Review Quality Gate
Review each document yourself against these **critical** quality bars:

1. **Factual**: Every claim must be verifiable. No imagined truth, no made-up knowledge, no hallucinated commands or APIs. If you're not confident something is accurate, research it again or flag it with a caveat.

2. **Clearly and concisely written**: Short sentences. Active voice. No filler. Every paragraph earns its place. Code examples are minimal but complete.

3. **Does not presume prior expertise**: A reader encountering this topic for the first time should be able to follow along. Define terms on first use. Explain *why*, not just *how*. Link to prerequisite documents where they exist.

If a document fails any quality bar, revise it before proceeding.

## Phase 6: Create Documents

For each approved document:

1. Write the file to the target directory using snake_case naming: `<directory>/<descriptive_name>.md`
2. Run `python3 .tools/fix_kb_ids.py <filepath>` to assign an ID and prefix the filename (use `--no-rename` for `projects/` directories)
3. Run `/doc-fix --auto-approve <final_filepath>` to normalize tags
4. Report the final filename and ID

## Phase 7: Report

Present a summary:
- Corpus analysis highlights (cluster count, gap count, new branch count)
- Topics proposed vs. topics selected
- Documents created (with final filenames and IDs)
- Key connections to existing documents (potential wiki-link candidates)
- Any topics that were researched but didn't meet quality bars (with explanation)
