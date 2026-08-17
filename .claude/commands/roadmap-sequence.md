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

Notes: closed/missing issues auto-drop and a chain that falls below 2 auto-dissolves; members are forced consecutive in the Backlog lane. If no numbers are given, that's the scan-everything recommend mode (#48, not built yet) — say so and ask for specific issue numbers. After any write, confirm the change in one line.
