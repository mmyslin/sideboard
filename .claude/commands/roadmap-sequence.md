---
description: Report or assemble a Sideboard sequence for the given issue numbers (targeted modes)
---
Handle a Sideboard **sequence** subcommand for arguments: `$ARGUMENTS`.

A *sequence* is an ordered chain of **≥2** Backlog/In-Progress issues with a short title; each issue is in **0 or 1** sequences. Read state from `http://127.0.0.1:7777/roadmap.json` — `sequences` is the array of existing chains `{id,title,items:[N,…]}`, and each item's `sequence` field is its current membership. Persist via the router API (POST JSON; sidecar-only and instant — the board's pill/modal reflects it on the next 2s poll):
- create: `POST /api/seq/create {"items":[N,…],"title":"…"}` → `{id}` (needs ≥2 existing issues; pulls any listed issue out of its old chain)
- rename / reorder: `POST /api/seq/update {"id":"seq-…","title"?:"…","items"?:[N,…]}`
- add / remove a member: `POST /api/seq/move {"number":N,"id":"seq-…"|null}` (null id = remove from its chain)
- dissolve: `POST /api/seq/dissolve {"id":"seq-…"}`

Parse issue numbers from `$ARGUMENTS` (ignore a leading `sequence` word if present).

**One number** (e.g. `12`) — report + propose a fit:
1. From roadmap.json, report the issue's **current** sequencing: if in a chain, name it (title) and show the full ordered chain marking this issue's position; otherwise say it's in none.
2. Judge the **right** sequence for it: read the issue (`gh issue view N`) and the relevant code / neighbouring issues to find real logical or technical dependencies. Recommend either joining an existing chain (which one, at what position) or forming a new one with specific issues — each with a concrete, code-grounded reason (e.g. "#17 imports the module #12 adds → #12 first").
3. Present the proposal and **ask to accept / reject / edit.** On accept, call the API (`seq/move` to join, `seq/create` for a new chain, `seq/update` to reposition). **Never write before the user accepts.**

**Two or more numbers** (e.g. `12 8 17`) — assemble into one sequence:
1. Read each issue (+ relevant code) to understand them.
2. Propose them as ONE chain, ordered by what makes **technical sense — not necessarily the order given.** Give the ordering a one-line rationale and a short (≤ ~4-word) title.
3. **Defer to the user:** default to trusting they want these grouped. Only if the grouping genuinely doesn't hold up (no dependency, a cycle, or they clearly belong in different chains) should you flag it and offer an alternative ordering or a split — but the user has final say over their grouping vs your suggestion.
4. Present and **ask to accept / reject / edit.** On accept, `POST /api/seq/create` with the final `items` + `title`. **Never write before accept.**

**No numbers** — recommend mode (scan Backlog + In Progress):
1. Read roadmap.json (all Backlog + In-Progress items + existing `sequences`), the issue bodies (`gh issue view`), and the relevant code/git to find **real** logical or technical dependencies — code-aware, not thematic. Only propose a chain where each step genuinely enables or precedes the next; **don't pad** with loose groupings (a good result is often zero or one recommendation).
2. Recommend NEW chains and UPDATES to existing ones, each with a short (≤ ~4-word) title and a one-line dependency rationale.
3. Present them as a **carousel in chat** via the `show_widget` tool (visualize): one card per recommendation — the title, the ordered chain (numbered #N + titles), the rationale, and **Accept / Edit / Dismiss** buttons. Accept and Edit call `sendPrompt(...)` with a clear message; Dismiss hides the card client-side. Multiple recs → a horizontal stepper/scroll; one → a single card.
4. On accept (the sendPrompt message), call the API — `seq/create` for a new chain, `seq/update` for an edit to an existing one — then confirm in one line. **Never write before an accept.**

Notes: closed/missing issues auto-drop and a chain that falls below 2 auto-dissolves; members are forced consecutive in the Backlog lane. After any write, confirm the change in one line.
