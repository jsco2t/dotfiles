---
name: tutorial-builder
description: "Research a topic and create a beginner-friendly hands-on tutorial with progressive runnable stages, explicit setup, exercises, expected results, and factual review. Use for saved tutorials rather than a live tutoring session."
---

# Tutorial Builder

Accept a topic and optional destination, audience, platform, or language. Ask only
for missing decisions that materially change the tutorial. For coding without a
specified or implied language, default to Go. Use `learning/<topic-slug>/` when
that matches the workspace; honor an explicit output location.

1. Research current primary documentation and exact commands/APIs. Establish
   versions, prerequisites, concept dependencies, and common beginner mistakes.
2. Propose the title, destination, part count, setup, progressive stages, and
   exercises. Obtain outline approval unless the caller already settled the
   structure or authorized direct drafting. A typical tutorial has four to eight
   stages, but use the number needed for a coherent learning progression.
3. Write stages that each introduce one capability and leave something working.
   Define new terms and explain purpose before mechanics. Supply explicit install,
   environment, and project setup steps. Use minimal complete examples that run
   at each stage, with language-tagged code blocks.
4. Each stage includes concept explanation, code/commands, **Try it** with exact
   actions and expected observations, and an explanation of the result. Add
   **Explore** experiments and common-pitfall guidance where useful. Show diagrams
   when they clarify the topic. Avoid leaps that assume unexplained knowledge.
5. Include frontmatter with `id`, `createdate`, `title`, and a `tutorial` tag plus
   useful topic tags, following corpus conventions. Use the corpus's timestamp
   convention, or the current local offset when none exists.
   In a notebook workspace, use `id: placeholder` only until its ID tool assigns
   the final ID; do not leave placeholders in a finished tutorial.
6. Run the bundled structural checker:

   ```bash
   python3 ~/.agents/skills/tutorial-builder/validate_tutorial.py <file-or-directory>
   ```

   Fix errors and assess warnings. Structural success does not verify factual
   claims or executable examples. Check examples safely when possible and clearly
   disclose anything not executed. Review with
   [doc-reviewer](~/.agents/skills/doc-reviewer/SKILL.md) and revise real issues.
7. In a notebook repository, follow [kb](~/.agents/skills/kb/SKILL.md) metadata/ID
   guidance, including its fixed `-07:00` timestamp convention. Run
   `~/.agents/skills/kb/scripts/fix_kb_ids.py` then
   `~/.agents/skills/kb/scripts/doc_fix.py` on each newly created tutorial only.
   Respect any existing no-rename convention. Else retain the target's own ID and
   tag conventions; do not depend on an unavailable formatting skill.
8. Update the existing tutorial index. When `learning/00_index.md` exists, follow
   its track tables and wiki-link convention, include key concepts, and use final
   filenames after ID assignment. Else follow the destination's navigation.

Report final paths, stages and exercises, checks performed, index changes, and
material limitations. For live teaching use
[teach-me-this](~/.agents/skills/teach-me-this/SKILL.md).
