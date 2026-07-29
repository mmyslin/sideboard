---
description: Bring up the VibeMap roadmap board in the preview pane
---
Bring up the VibeMap roadmap board — do just this, quickly, nothing else:

1. Make sure the companion is running on port 7777. From the directory that
   contains `github_companion.py`, run in Bash:
   `curl -sf -o /dev/null --max-time 1 http://127.0.0.1:7777/roadmap-board.html || nohup python3 github_companion.py >/tmp/vibemap-companion.log 2>&1 &`
2. Open `http://127.0.0.1:7777/roadmap-board.html` in the preview/browser pane
   (use preview_start with that url, or navigate the existing pane to it).
3. Confirm in one short line that the board is up.
