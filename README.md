# vibemap

A live, always-visible **project roadmap** for [Claude Code](https://claude.com/claude-code) — a little kanban board that sits next to your chat and updates itself as you work.

Claude Code has no API for custom sidebar panels, but the redesigned desktop app lets you pin any local web page in the **preview pane** beside chat. vibemap is that page: a single self-contained HTML board backed by a `roadmap.json` file. A companion **skill** teaches Claude to keep the JSON up to date during normal conversation — adding features you decide to build, flipping items to *in progress* when work starts, marking them *done* when it lands. The board polls the file every 2 seconds, so it moves on its own.

```
┌─ chat ──────────────┐┌─ roadmap ───────────────────────┐
│                     ││ Backlog │ Next │ In Progress │ … │
│  you + Claude       ││   ▢     │  ▢   │     ▣▣       │ … │
│                     ││                                  │
└─────────────────────┘└──────────────────────────────────┘
```

## How it works

- **`roadmap.json`** (in your project root) is the single source of truth: a list of items, each with `id`, `title`, `status`, `notes`, and `updated_at`.
- **`roadmap-board.html`** is a zero-dependency kanban view. It fetches `roadmap.json` every 2s, renders four columns (Backlog → Next Up → In Progress → Done), and briefly glows any item touched in the last 30 seconds. Light and dark themes are automatic.
- **The `vibemap` skill** tells Claude when and how to edit `roadmap.json` — proactively, as part of normal work — so the board reflects reality without you micromanaging it.

There's no MCP server and no hook: updates flow through Claude editing the file during chat. That keeps setup to zero infrastructure. (If you later want the board to update outside of an active session, that's the point to graduate to an MCP server.)

## Install

```bash
git clone https://github.com/mmyslin/vibemap.git
cd vibemap
./install.sh
```

This copies the skill and board into `~/.claude/skills/vibemap/`. Start a new Claude Code session and the `/vibemap` skill is available everywhere.

## Use

In any project, just ask Claude to **"set up the roadmap"** (or run `/vibemap`). Claude will:

1. Create a `roadmap.json` seeded from your conversation.
2. Copy `roadmap-board.html` into the project.
3. Serve the folder locally: `python3 -m http.server 7777`
4. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview pane.

Drag the preview pane beside your chat and **save the layout** so it persists. From then on, as you and Claude decide what to build, the board keeps itself current.

To restart the board server later:

```bash
cd your-project && python3 -m http.server 7777
# then open http://127.0.0.1:7777/roadmap-board.html
```

## Notes

- The board is served over `127.0.0.1` (localhost only). It exposes the folder it's served from, so serve your project root, not your home directory. Don't bind it to `0.0.0.0`.
- Commit `roadmap.json` if you want the roadmap in version control. The board HTML is a dev tool — gitignoring it per-project is fine.
- Requires the redesigned Claude Code desktop app (the one with the preview pane) to pin the board beside chat. Any browser works too — it's just a local web page.

## License

MIT © 2026 Mark Myslin
