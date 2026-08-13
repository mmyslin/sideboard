---
description: Open the VibeMap roadmap board in the preview pane
---
Open the VibeMap roadmap board — nothing else. The router is already running (the
session hook boots it), so this must be as fast/cheap as possible.

In ONE response: write just "Board's up." AND in that same response call
preview_start once with url `http://127.0.0.1:7777/roadmap-board.html`. That's
it — the confirmation is optimistic so you don't spend a second turn on it.

Do NOT run Bash, navigate, screenshot, read the page, or otherwise verify. After
the tool result, add nothing further — unless preview_start clearly failed, in
which case run `./vibemap-up.sh` once, retry preview_start, and stop.
