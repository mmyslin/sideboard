---
name: sideboard
description: Maintain and display a live project roadmap/kanban board backed by GitHub Issues. Use when the user asks to see, set up, or update the roadmap, add a feature to build next, mark an item in-progress or done, or when a chat naturally decides on upcoming work worth tracking. Manages the roadmap via `gh` (GitHub Issues) and serves a live board in the preview pane.
---

# sideboard — live roadmap board (GitHub Issues)

A project's roadmap **is its GitHub Issues.** The board (`roadmap-board.html`),
served by the router (`sideboard_router.py`) on :7777, renders those issues as a
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
- **`.sideboard/meta.json`** (committed sidecar) holds what GitHub doesn't: the
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
- An open item is already implemented, or duplicates another → the **`/roadmap-cleanup`** command flags it with code evidence and closes/merges it on your OK.
- Need fresh items (or a board from scratch on a new project) → the **`/roadmap-suggest`** command mines the repo (TODOs, stubs, churn, gaps, unbuilt promises) and seeds issues on your OK.

Keep titles terse — this is a glanceable board, not a spec. Mention roadmap
changes in one short line; don't derail the main task. **Do not create or edit a
`roadmap.json`** — local-file mode no longer exists.

## Referring to cards by number
`#N` means the **GitHub issue number** — `#10`, "do #10", "move #7 to in
progress", "close out #3". Resolve it to issue N and act (implement it, change
status, edit, or just answer). If no issue N exists, say so plainly rather than
guessing at the closest match.

## Sequences
A **sequence** is an ordered chain of **≥2** Backlog/In-Progress issues (each issue in **0 or 1**) with a short title — a build-order / dependency hint. It lives in the sidecar; the board shows a linked-rings pill on chained cards (click it for a drag-reorderable modal), draws a bracket connector down the chain in the Backlog lane, and keeps a chain's cards consecutive. Manage via the router API (POST JSON, instant): `/api/seq/create {items,title}`, `/api/seq/update {id,title?,items?}`, `/api/seq/move {number,id|null}`, `/api/seq/dissolve {id}`. Read current chains from `roadmap.json` (`sequences` + each item's `sequence`).

Propose **dependency-grounded** orderings (code-aware — reason from what the code/issues actually are, not just titles) and let the user **accept / reject / edit** before writing. The **`/roadmap-sequence <N…>`** command drives the targeted modes: one number → report its current chain + propose a fit; several numbers → assemble them into one chain in the order that makes technical sense (defer to the user on whether they belong together).

### Acting on a sequenced issue (disposition)
Sequences are dependency hints — honor them when starting or finishing work. Find a chain from the sidecar `.sideboard/meta.json` `sequences` (or `roadmap.json`'s `sequences` + each item's `sequence` when the board is serving this project); a member is **done when its issue is closed**.

- **Before starting / moving an issue to In Progress** ("start #N", "do #N", "let's build #N"): if #N is in a chain and **any earlier member is still open** (an unfinished predecessor), **check in first** — name the chain and the specific open predecessor(s), and ask whether to start the predecessor instead or go ahead with #N. A nudge, not a block — the user decides.
- **After closing an issue** in a chain: if the **next** still-open member exists, **suggest it** in one line — e.g. "#N done — next in «Title» is #M: <title>. Start it?"

One short line either way; don't derail the task.

## Setup / bootstrap (first run in a project)
1. Confirm prerequisites above (`gh auth status`, Issues enabled on the repo).
2. Create the sidecar so the router discovers the project:
   `mkdir -p .sideboard && printf '{"schema": 1}\n' > .sideboard/meta.json` — then
   commit it. The router reconciles it from your existing issues on first sync
   (all open issues start in Backlog; reorder/split by dragging on the board).
3. Start the board server. It normally comes up on its own — the plugin's
   SessionStart hook (`sideboard-active.sh`) boots it for you — so it's usually
   already serving :7777. If it isn't, run the bundled `sideboard-up.sh` launcher
   (plugin: `${CLAUDE_PLUGIN_ROOT}/scripts/sideboard-up.sh`; legacy install:
   `~/.claude/skills/sideboard/sideboard-up.sh`). It follows the active project.
4. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview pane and dock
   it beside chat.

## Displaying on demand
If the router is already running, just re-open
`http://127.0.0.1:7777/roadmap-board.html` (or use the `/roadmap` command). The
board auto-refreshes; you never reload it after a `gh` change — the next 2s poll
picks it up.
