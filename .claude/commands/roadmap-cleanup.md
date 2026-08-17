---
description: Scan the roadmap for issues that are already done or redundant, and propose closing/merging them
---
Groom the active Sideboard project's roadmap: find **open** issues (Backlog + In-Progress) that no longer earn a spot — **already done** or **redundant** — and propose closing/merging them. List the open issues with `gh issue list --state open` (or read `http://127.0.0.1:7777/roadmap.json`). The active project is the repo you're in / the one the board is serving.

Judge each open issue with the **code**, not just its title:

**A. Already done** — reality overtook the issue: the thing it asks for is implemented. **Confirm with evidence** before flagging — a `file:line`, a function/endpoint/flag, or a commit (grep/read the code; check `git log`). A vague hunch is not enough; if you can't point at where it's done, don't flag it.

**B. Redundant** — the issue duplicates or is fully subsumed by another issue (open, or already closed). Name the specific **#M** and how they overlap.

Present findings as a short list — for each: `#N <title>` → **action** (close, or merge into #M) + a one-line, code-grounded reason (cite the `file:line`/commit for "done"). If nothing qualifies, **say so plainly** — a clean roadmap is a fine result; don't invent findings.

**Ask which to apply. Never close or merge before the user confirms.** On confirm:
- done → `gh issue close <N> --comment "<why + the evidence you cited>"`
- redundant → `gh issue close <N> --comment "Merged into #M — <why>."` (keep the more complete/earlier issue; first move any unique detail from #N into #M if it'd be lost)

After applying, confirm in one line — the board drops the closed cards on its next poll. Keep the whole thing terse; this is grooming, not a report.
