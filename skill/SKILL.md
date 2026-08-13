---
name: vibemap
description: Maintain and display a live project roadmap/kanban board backed by GitHub Issues. Use when the user asks to see, set up, or update the roadmap, add a feature to build next, mark an item in-progress or done, or when a chat naturally decides on upcoming work worth tracking. Manages the roadmap via `gh` (GitHub Issues) and serves a live board in the preview pane.
---

# vibemap — live roadmap board (GitHub Issues)

A project's roadmap **is its GitHub Issues.** The board (`roadmap-board.html`),
served by the router (`vibemap_router.py`) on :7777, renders those issues as a
live kanban board and polls every 2s. Pin it in the Claude Code desktop preview
pane next to chat for an always-visible, auto-updating roadmap.

There is **one mode: GitHub.** Manage the roadmap with `gh`, not a local file.

## Prerequisites
- A git repo with a GitHub remote, **Issues enabled**.
- `gh` installed and authenticated (`gh auth login`).
- `python3` on PATH (runs the local board server).

## Data model
- **Each roadmap card is a GitHub issue.** `#N` = the issue number.
- **Status → column:**
  - open issue, sidecar status `backlog` → **Backlog**
  - open issue, sidecar status `in_progress` → **In Progress**
  - **closed issue → Done** (closing an issue *is* marking it done; reopening moves it back)
- **Feature tags** are GitHub **labels**, shown as small-caps chips with stable per-tag colors.
- **`.vibemap/meta.json`** (committed sidecar) holds what GitHub doesn't: the
  backlog/in_progress split, card order, and per-tag color assignments. The
  router **reconciles it automatically** on every sync — GitHub wins for
  content and open/closed; the sidecar wins for swimlane split and order. You
  normally never hand-edit it.

## Updating the roadmap (do this proactively, without being asked)
Keep the board honest during normal work, using `gh`:
- User decides to build something → `gh issue create --title "…" [--body "…"]` (lands in Backlog).
- You start on an item → move it to In Progress (drag on the board, or it's the sidecar `status`; the board's move does this for you).
- Work lands / user confirms done → `gh issue close <N>`. Reopen with `gh issue reopen <N>`.
- Scope/notes change → `gh issue edit <N> --title/--body`.
- Add/remove a feature tag → `gh issue edit <N> --add-label "<tag>"` / `--remove-label`.

Keep titles terse — this is a glanceable board, not a spec. Mention roadmap
changes in one short line; don't derail the main task. **Do not create or edit a
`roadmap.json`** — local-file mode no longer exists.

## Referring to cards by number
`#N` means the **GitHub issue number** — `#10`, "do #10", "move #7 to in
progress", "close out #3". Resolve it to issue N and act (implement it, change
status, edit, or just answer). If no issue N exists, say so plainly rather than
guessing at the closest match.

## Setup / bootstrap (first run in a project)
1. Confirm prerequisites above (`gh auth status`, Issues enabled on the repo).
2. Create the sidecar so the router discovers the project:
   `mkdir -p .vibemap && printf '{"schema": 1}\n' > .vibemap/meta.json` — then
   commit it. The router reconciles it from your existing issues on first sync
   (all open issues start in Backlog; reorder/split by dragging on the board).
3. Start the board server: run `~/.claude/skills/vibemap/vibemap-up.sh` (starts
   the router on :7777, following the active project).
4. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview pane and dock
   it beside chat.

## Displaying on demand
If the router is already running, just re-open
`http://127.0.0.1:7777/roadmap-board.html` (or use the `/roadmap` command). The
board auto-refreshes; you never reload it after a `gh` change — the next 2s poll
picks it up.
