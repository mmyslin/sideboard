---
name: vibemap
description: Maintain and display a live project roadmap/kanban board. Use when the user asks to see, set up, or update the roadmap, add a feature to build next, mark an item in-progress or done, or when a chat naturally decides on upcoming work worth tracking. Reads and writes roadmap.json in the project root and serves a live board in the preview pane.
---

# vibemap — live roadmap board

A per-project roadmap kept in `roadmap.json` at the project root, rendered as a
live kanban board (`roadmap-board.html`) that polls the JSON every 2s. Pin the
board in the Claude Code desktop preview pane next to chat for an always-visible,
auto-updating roadmap.

## Data model — `roadmap.json`

```json
{
  "project": "Project Name",
  "seq": 24,
  "updated_at": "2026-01-01T00:00:00Z",
  "items": [
    { "id": "kebab-id", "ref": 12, "title": "Short feature title",
      "status": "backlog|next|in_progress|done",
      "notes": "optional one-liner",
      "updated_at": "2026-01-01T00:00:00Z" }
  ]
}
```

- **Statuses / columns:** `backlog` → Backlog, `next` → Next Up, `in_progress` → In Progress, `done` → Done.
- `id` is a stable kebab-case slug; never reuse or renumber ids.
- `ref` is the card's human-facing number (shown as `#N`). When adding an item, set its `ref` to the top-level `seq`, then increment `seq`. **Never reuse a ref**, even after an item is deleted — always hand out `seq` and bump it.
- Every write updates the changed item's `updated_at` AND the top-level `updated_at`, both ISO-8601 UTC.

## When to update (do this proactively, without being asked)

During normal work, keep the board honest:
- The user decides to build something next → add an item (`backlog` or `next`).
- You start working on an item → set it `in_progress`.
- Work lands / user confirms done → set it `done`.
- Scope/notes change → edit `notes`.

Make the edit by reading `roadmap.json`, modifying the item, and writing it back
as valid JSON. Keep it terse — this is a glanceable board, not an issue tracker.
Mention roadmap changes in one short line; don't derail the main task.

## Setup / bootstrap (first run in a project)

If `roadmap.json` does not exist in the project root:
1. Copy the board next to it: `cp ~/.claude/skills/vibemap/roadmap-board.html <project>/roadmap-board.html`
2. Create `roadmap.json` with the project name and any items evident from the chat (else an empty `items: []`).
3. Serve the project root so the board can fetch the JSON over http (file:// blocks the fetch):
   `cd <project> && python3 -m http.server 7777` (run in background).
4. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview pane, then drag/save the layout so it sits beside chat.

Suggest adding `roadmap-board.html` to `.gitignore` if the board shouldn't be committed (`roadmap.json` is usually worth committing).

## Displaying on demand

If the server is already running, just re-open `http://127.0.0.1:7777/roadmap-board.html`.
The board auto-refreshes; you never need to reload it after a JSON edit.
