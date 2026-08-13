---
description: Open the VibeMap roadmap board in the preview pane
model: haiku
effort: low
---
Open the VibeMap roadmap board. This is a TRIVIAL one-step task — do not think,
plan, analyze, or deliberate. The router is already running (the session hook
boots it).

Do exactly this, nothing more:
1. Call preview_start ONCE with url `http://127.0.0.1:7777/roadmap-board.html`.
2. After the result, reply with ONE short line (e.g. "Board's up.") and STOP.

No Bash, navigate, screenshot, page reading, or verification. No further
reasoning or actions after step 2. Only if preview_start clearly failed: run
`./vibemap-up.sh` once, retry, stop.
