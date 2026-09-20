---
name: kb
description: Create one or more standalone Markdown knowledge-base articles from supplied material or prior conversation and write them to an explicitly supplied output location. Use when the user asks to capture a topic as KB entries; requires both an output location and a topic, and applies notebook-specific frontmatter, IDs, and filenames when the target is inside a Git repository named notebook.
---

# Knowledge Base Articles

Turn source material into durable reference documentation rather than a transcript or chat summary. Preserve useful technical detail while making each article independently understandable and easy to retrieve later.

## Require both inputs

The invocation has this structure:

```text
<output location> <kb topic>
```

Both values are mandatory.

- The output location is the directory or Markdown file where the article should be created. Resolve relative locations from the directory where the skill was invoked.
- The topic may be pasted content, notes, a named subject, or a clear reference to something discussed earlier in the conversation.

If either value is missing, ask the user for the missing value and wait before creating anything. Do not default the output location to the current directory, and do not invent a topic from unrelated context. When a reference such as "this" could identify more than one prior subject, ask which subject the user means.

Treat a location ending in `.md` as a requested single output file. Otherwise treat it as a directory, creating it when necessary. If a topic should clearly become multiple articles but the user supplied a file path, keep it as one coherent article or ask for a directory; never create unrequested sibling files beside an explicit file.

## Use the available source material

When the topic refers to the current conversation, incorporate the relevant conclusions, examples, corrections, and code traces already established. For example, after an `explain-this` session, turn the resulting code understanding into a stable reference without requiring the user to paste the discussion again.

Inspect referenced local material when needed to make the article accurate. Complete partial ideas when the missing connection is supported by the available evidence. Do not fabricate commands, behavior, or rationale; call out a genuine uncertainty or ask a focused question when it would materially affect correctness.

## Decide article boundaries

Use judgment to produce one or more articles. Give each article one primary retrieval intent: the question or task for which someone would search later.

Split the material when it contains independently useful concepts, unrelated procedures, distinct systems, or sections likely to evolve separately. Keep it together when the sections form one workflow, rely heavily on the same setup, or would become repetitive and fragmentary if separated. Prefer a small number of substantial entries over many thin ones.

For every article:

- choose a specific, descriptive title;
- open with the purpose and the situation in which the information is useful;
- organize the content with clear headings and concise, actionable prose;
- preserve important prerequisites, commands, examples, expected results, caveats, and failure modes;
- use fenced code blocks with accurate language identifiers;
- include a table of contents only when the article is long enough to benefit from one;
- retain useful source links or provenance when they are available.

Avoid chat artifacts, repeated conclusions, generic filler, and unexplained references to "above" or "earlier." A reader should not need the original conversation to use the article.

## Detect notebook mode

Before naming or writing files, resolve the output location to an absolute path. Starting from the location or its nearest existing parent, use Git to find the repository root. Notebook mode applies only when the output is inside a Git worktree whose repository-root directory is named `notebook`. Do not infer notebook mode merely because another path component contains that word.

Honor the output location exactly; notebook mode does not implicitly redirect output to a different directory such as `kb/`.

## Write ordinary Markdown outside a notebook repository

Inspect nearby documents and applicable repository guidance for local conventions. When the output is a directory and no stronger convention exists, use a concise `snake_case.md` filename. Do not add notebook IDs or run the bundled notebook maintenance scripts outside notebook mode.

Never overwrite an existing article unless the user explicitly asked to replace or update it. Choose a more specific non-conflicting filename when that preserves the user's intent; ask when it does not.

## Write articles in notebook mode

The helper scripts are bundled with this skill. Refer to them from the directory containing this `SKILL.md`; do not use copies from the target repository.

For each new article:

1. Create a temporary semantic filename in the requested output directory using `snake_case.md` with no ID prefix.
2. Add this YAML frontmatter before the article body:

   ```yaml
   ---
   id: placeholder
   createdate: YYYY-MM-DDTHH:MM:SS-07:00
   title: Descriptive Article Title
   tags:
     - relevant-tag
   ---
   ```

   Use the current date and time with the fixed `-07:00` offset used by the notebook tooling. Choose focused lowercase tags; the cleanup script enforces normalization, exclusions, deduplication, and a ten-tag maximum.

3. Run the bundled ID tool against that new file only, using absolute paths:

   ```bash
   python3 <skill-directory>/scripts/fix_kb_ids.py <absolute-draft-path>
   ```

   Capture the final renamed path. The tool replaces the placeholder with an eight-character Crockford Base32 ID and prefixes the filename with the same ID.

4. If multiple new articles should link to each other, assign all IDs first and then add links using their final filenames or stems. Do not leave links pointing at the temporary semantic filenames.
5. Run the bundled document cleanup tool against each final file individually, again using absolute paths:

   ```bash
   python3 <skill-directory>/scripts/doc_fix.py <absolute-final-path>
   ```

   This normalizes and suggests tags and refreshes an existing table of contents. The newly created article is already authorized, so no separate dry-run approval cycle is needed.

Never run either helper over the whole output directory: doing so could rename or rewrite pre-existing documents outside the requested work.

After the tools finish, verify each new document rather than trusting command output alone:

- the filename is `<8-character-id>_<snake_case_name>.md`;
- the frontmatter `id` exactly matches the filename prefix;
- `createdate`, `title`, and `tags` are present and valid;
- the Markdown body is complete and any inter-article links use final names.

## Report the result

List every final article path and title. In notebook mode, include its assigned ID. When the topic was split, briefly state the boundary used so the user can judge whether the grouping is useful. Do not commit or push the new documents unless the user separately requests it.
