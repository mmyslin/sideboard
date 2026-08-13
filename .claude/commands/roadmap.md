---
description: Open the VibeMap roadmap board in the preview pane
model: haiku
effort: low
---
Open the VibeMap roadmap board. This is a TRIVIAL one-step task — do not think,
plan, analyze, or deliberate. The router is already running.

REUSE the existing pane tab instead of opening a new one (a new tab is slow to
cold-open and clutters the pane):

1. Call navigate with url `http://127.0.0.1:7777/roadmap-board.html` — this
   reuses the current tab, no new tab.
2. ONLY if navigate errors that no preview/pane is open, call preview_start once
   with that same url.
3. Reply with ONE short line (e.g. "Board's up.") and STOP.

No Bash, screenshot, page reading, or verification. No further reasoning or
actions after step 3.
