# vibemap

A live, always-visible **project roadmap** for [Claude Code](https://claude.com/claude-code) — a little kanban board that sits next to your chat and updates itself as you work. **Your GitHub Issues, as a live board in Claude Code.**

Claude Code has no API for custom sidebar panels, but the redesigned desktop app lets you pin any local web page in the **preview pane** beside chat. vibemap is that page: a self-contained HTML board whose source of truth is your repo's **GitHub Issues**. A companion **skill** teaches Claude to keep the roadmap current with `gh` during normal conversation — filing what you decide to build, moving items to *in progress*, closing them *done* when work lands. The board polls every 2 seconds, so it moves on its own.

```
┌─ chat ──────────────┐┌─ roadmap ───────────────────┐
│                     ││ Backlog │ In Progress │ Done │
│  you + Claude       ││   ▢     │     ▣▣      │  ▣▣  │
│                     ││                              │
└─────────────────────┘└──────────────────────────────┘
```

## How it works

- **GitHub Issues are the source of truth.** Each roadmap card is an issue; `#N` is its issue number. A **closed issue = Done**.
- **`.vibemap/meta.json`** (a small committed sidecar) holds what GitHub doesn't: the Backlog↔In Progress split, card order, and per-tag colors. The router **reconciles it automatically** — GitHub wins for content and open/closed; the sidecar wins for lane split and order.
- **`vibemap_router.py`** serves the board on `127.0.0.1:7777` and, on each sync, rebuilds it from `gh issue list` + the sidecar. One router serves *all* your projects and follows whichever one you're working in.
- **`roadmap-board.html`** is a zero-dependency kanban view — three columns (Backlog → In Progress → Done), feature-tag chips, drag to move/reorder, add/edit inline. Light and dark themes are automatic.
- **The `vibemap` skill** tells Claude when and how to update the roadmap via `gh`, proactively, as part of normal work.
- **A global hook** posts your active session's title to the router so the pinned pane follows the project you're in (see `docs/` and issue #35).

## Prerequisites

- A git repo with a **GitHub remote and Issues enabled**.
- **`gh`** installed and authenticated (`gh auth login`).
- **`python3`** on PATH (runs the local board server).

## Install

```bash
git clone https://github.com/mmyslin/vibemap.git
cd vibemap
./install.sh
```

This copies the skill, board, router, and activity hook into `~/.claude/skills/vibemap/` and wires the hook into your settings. Start a new Claude Code session and the `/vibemap` skill + `/roadmap` command are available everywhere.

> A one-command **Claude Code plugin** install is planned (issue #12) to replace the clone-and-run step.

## Use

In any repo that meets the prerequisites, ask Claude to **"set up the roadmap"** (or run `/vibemap`). Claude will:

1. Bootstrap the sidecar so the router discovers the project:
   ```bash
   mkdir -p .vibemap && printf '{"schema": 1}\n' > .vibemap/meta.json
   ```
   Commit it. The router reconciles it from your existing issues on first sync (all open issues start in Backlog; reorder and split lanes by dragging).
2. Start the board: `./vibemap-up.sh` (or `~/.claude/skills/vibemap/vibemap-up.sh`).
3. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview pane.

Drag the pane beside your chat and **save the layout**. From then on, as you and Claude decide what to build — and as `gh issue` changes land — the board keeps itself current. Re-open it any time with `/roadmap`.

## Scoping: everywhere, one project, or off

Where you put the skill folder decides where `/vibemap` is available. Claude Code picks up added/edited/removed skills live — no restart needed (the one exception is creating `~/.claude/skills/` for the very first time).

**Everywhere (all your projects).** This is what `install.sh` does — it installs to `~/.claude/skills/vibemap/`, which every project reads, on all surfaces (CLI, desktop app, IDE extension).

**Just one project.** Drop the folder at `<project>/.claude/skills/vibemap/` and commit it; `/vibemap` then exists only in that repo, and anyone who clones it gets the board for free. If the skill exists both globally and in a project, the **project copy wins** there.

**Turn it off without deleting it.** Use `skillOverrides` in `.claude/settings.json` (per project) or `~/.claude/settings.json` (global):

```json
{ "skillOverrides": { "vibemap": "off" } }
```

- `"on"` — active (default)
- `"off"` — hidden everywhere
- `"user-invocable-only"` — Claude won't trigger it automatically, but you can still run `/vibemap`
- `"name-only"` — listed without its description

Run `/skills` to see every skill and its current state.

## Notes

- The board is served over `127.0.0.1` (localhost only). Don't bind it to `0.0.0.0`.
- `.vibemap/meta.json` is meant to be **committed** — it carries your lane split, order, and tag colors. The board HTML is a dev tool; gitignoring a per-project copy is fine.
- Requires the redesigned Claude Code desktop app (the one with the preview pane) to pin the board beside chat. Any browser works too — it's just a local web page.

## License

MIT © 2026 Mark Myslin
