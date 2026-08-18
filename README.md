# Sideboard

**Your GitHub Issues as a live roadmap board in Claude Code.**

Sideboard shows your repo's GitHub Issues as a live roadmap board that you and [Claude Code](https://claude.com/claude-code) drive together. Quickly log ideas for the backlog, start Claude on the next issue, and reason across your roadmap **and** codebase in context — no need to jump out of Claude Code to an external board.

<img width="3300" height="1771" alt="sideboard" src="https://github.com/user-attachments/assets/fa8e6c52-b8d9-4615-9c85-79ada1c75024" />

Claude Code has no API for custom side panels, but its desktop app lets you pin any local web page in the **preview pane** next to chat. Sideboard is that page: a zero-dependency HTML board whose source of truth is your **GitHub Issues**. A companion **skill** teaches Claude to keep the board current with `gh` during normal conversation — filing what you decide to build, moving cards to *In Progress*, closing them *Done* when work lands. It polls every 2 seconds, so it moves on its own.

## Code-aware roadmap skills

Because Claude holds your roadmap **and** your codebase in context, Sideboard ships commands that reason across both — and they always propose first, never acting until you accept:

- **`/roadmap-suggest`** — mines the repo for work the board is missing (TODOs, stubs, churn-heavy files, gaps, features the docs promise) and offers them as a checklist. On a brand-new project it bootstraps a starter backlog from scratch.
- **`/roadmap-sequence`** — finds dependency chains: report or assemble specific issues, or scan the board and recommend build-orders in a chat carousel. The board draws each chain as a connector down the lane.
- **`/roadmap-cleanup`** — flags issues that are already done (confirmed against the actual code) or redundant, and closes/merges them on your OK.

## How it works

- **GitHub Issues are the source of truth.** Each card is an issue; `#N` is its number; a **closed issue = Done**.
- **`.sideboard/meta.json`** — a small committed sidecar — holds what GitHub doesn't: the Backlog↔In Progress split, card order, tag colors, and dependency sequences. The router reconciles it automatically — GitHub wins for content and open/closed; the sidecar wins for lane split and order.
- **`sideboard_router.py`** serves the board on `127.0.0.1:7777`, rebuilding it from `gh issue list` + the sidecar on each sync. One router serves *all* your projects and follows whichever one you're working in.
- **`roadmap-board.html`** is a zero-dependency kanban — three columns (Backlog → In Progress → Done), feature-tag chips, drag to move/reorder, add/edit inline. Light and dark themes are automatic.

## Prerequisites

- A git repo with a **GitHub remote and Issues enabled**.
- **`gh`** installed and authenticated (`gh auth login`).
- **`python3`** on PATH (runs the local board server).

## Install

```bash
git clone https://github.com/mmyslin/sideboard.git
cd sideboard
./install.sh
```

Installs the skill, board, router, commands, and activity hook into `~/.claude/skills/sideboard/`, and wires the hook into your settings. Start a new Claude Code session and `/roadmap` (plus the code-aware commands above) are available in every project.

> **Distribution:** the intended path is a one-command **Claude Code plugin** (issue [#12](https://github.com/mmyslin/sideboard/issues/12)) — `/plugin install …` instead of clone-and-run, with no `settings.json` editing. This README will be reframed around the plugin flow when that ships.

## Use

In any repo that meets the prerequisites, ask Claude to **"set up the roadmap"** (or run `/roadmap`). Claude bootstraps the sidecar so the router discovers the project, starts the board (`./sideboard-up.sh`), and opens `http://127.0.0.1:7777/roadmap-board.html` in the preview pane. Drag the pane beside your chat and **save the layout** — from then on, as you and Claude decide what to build and as `gh issue` changes land, the board keeps itself current. Re-open it any time with `/roadmap`.

## Notes

- The board is served on `127.0.0.1` (localhost only). Don't bind it to `0.0.0.0`.
- `.sideboard/meta.json` is meant to be **committed** — it carries your lane split, order, tag colors, and sequences. The board HTML itself is a dev tool; a gitignored per-project copy is fine.
- Requires the Claude Code desktop app (the one with the preview pane) to pin the board beside chat. Any browser works too — it's just a local web page.

## License

MIT © 2026 Mark Myslin
