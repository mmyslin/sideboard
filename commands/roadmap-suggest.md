---
description: Mine the repo for new roadmap items — or, on a fresh project, bootstrap the board from scratch
---
Suggest roadmap items for the active Sideboard project by mining the **repo itself**, not just the existing issues. First detect the state:

**Cold start** — no `.sideboard/meta.json` sidecar, or `gh issue list` returns no issues: this is a brand-new board, so **bootstrap** it.
1. Confirm prerequisites: a git repo with a GitHub remote, Issues enabled, `gh` authed (`gh auth status`).
2. Scan the repo for what the roadmap should hold — the README (a roadmap/TODO section, "coming soon", unchecked task lists), `TODO`/`FIXME`/`HACK` comments, and obvious missing pieces (no tests, no CI, no error handling, stubbed functions, features the docs promise but the code lacks).
3. Propose a **starter backlog** — a handful of concrete, terse issues grounded in what you found (cite where each came from).
4. On the user's OK: create the sidecar so the router discovers the project — `mkdir -p .sideboard && printf '{"schema": 2}\n' > .sideboard/meta.json` (commit it) — then `gh issue create` each accepted item. Offer to start the board (the `sideboard-up.sh` launcher — plugin: `${CLAUDE_PLUGIN_ROOT}/scripts/sideboard-up.sh`, legacy install: `~/.claude/skills/sideboard/sideboard-up.sh`; the SessionStart hook usually has it up already) and open it.

**Existing roadmap** — sidecar + issues already present: mine for **NEW** items the board is missing.
- `TODO`/`FIXME`/`HACK`/`XXX` comments (grep the tree) → an item each, or grouped if many.
- Failing or skipped tests; churn-heavy files (`git log` shows repeated patches → a latent bug/refactor); stubbed functions (`NotImplementedError`, `pass`-only, obvious placeholders).
- Gaps a reader would expect — missing tests / CI / docs / error handling — and unbuilt features the README or docs already promise.
- **Cross-check against the open issues — never propose anything already tracked.**

Present the suggestions as a **checklist in chat** via the `show_widget` tool (visualize): one row per suggestion — an **Add checkbox (checked by default)**, the terse title, and the one-line code-grounded reason (cite the `file:line`/pattern/commit) — plus a **Create selected** button that `sendPrompt`s the checked titles back. If the repo is genuinely well-covered, **say so plainly** (no widget needed); don't pad.

**Nothing is created until the user clicks Create selected.** On that message, `gh issue create --title "…" [--body "…"]` each checked item (terse titles — a glanceable board, not a spec; lands in Backlog). Confirm in one line — the board picks them up on its next poll.
