---
description: Open the VibeMap roadmap board in the preview pane
---
Open the VibeMap roadmap board — nothing else. The router is already running (the
session hook boots it), so do NOT run Bash, screenshot, read the page, or verify.

1. Call preview_start ONCE with url `http://127.0.0.1:7777/roadmap-board.html`
   (it opens or reuses the pane in a single step — do NOT try navigate first).
2. Reply with one short line, e.g. "Board's up."

Only if the pane genuinely fails to load: run `./vibemap-up.sh` once, retry the
open, and stop. Never screenshot to confirm.
