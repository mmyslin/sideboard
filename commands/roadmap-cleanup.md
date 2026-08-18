---
description: Scan the roadmap for issues that are already done or redundant, and propose closing/merging them
---
Groom the active Sideboard project's roadmap: find **open** issues (Backlog + In-Progress) that no longer earn a spot — **already done** or **redundant** — and propose closing/merging them. List the open issues with `gh issue list --state open` (or read `http://127.0.0.1:7777/roadmap.json`). The active project is the repo you're in / the one the board is serving.

Judge each open issue with the **code**, not just its title:

**A. Already done** — reality overtook the issue: the thing it asks for is implemented. **Confirm with evidence** before flagging — a `file:line`, a function/endpoint/flag, or a commit (grep/read the code; check `git log`). A vague hunch is not enough; if you can't point at where it's done, don't flag it.

**B. Redundant** — the issue duplicates or is fully subsumed by another issue (open, or already closed). Name the specific **#M** and how they overlap.

Present the findings as a **checklist in chat** via the `show_widget` tool (visualize): one row per finding — an **Apply checkbox (checked by default)**, `#N <title>` → the action (close, or merge into #M), and the one-line code-grounded reason (cite the `file:line`/commit for "done") — plus a **Close selected issues** button that `sendPrompt`s the checked findings back. If nothing qualifies, **say so plainly** (no widget) — a clean roadmap is a fine result; don't invent findings.

**Nothing is closed or merged until the user clicks Close selected issues.** On that message:
- done → `gh issue close <N> --comment "<why + the evidence you cited>"`
- redundant → `gh issue close <N> --comment "Merged into #M — <why>."` (keep the more complete/earlier issue; first move any unique detail from #N into #M if it'd be lost)

Confirm in one line — the board drops the closed cards on the router's next GitHub sync (~45s). Keep it terse; this is grooming, not a report.
