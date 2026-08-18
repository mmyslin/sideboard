---
description: Open the Sideboard roadmap board in the preview pane
model: haiku
effort: low
---
Open my Sideboard roadmap board. The router is already running on :7777.

1. Run `cat ~/.claude/sideboard-token 2>/dev/null` (Bash) to read the board's
   auth token. Build the board url: if you got a token, use
   `http://127.0.0.1:7777/roadmap-board.html?token=<TOKEN>` (substituting the
   value); if the file was empty or missing, use the url without `?token=`.

2. Call navigate with that url to reuse the existing pane tab. ONLY if navigate
   errors that no preview/pane is open, call preview_start once with that same url.

3. Take ONE screenshot to confirm the board rendered — you should see the PROJECT
   header and the Backlog / In Progress / Done columns. If the pane is blank, or the
   board is collapsed into a short strip at the top with empty space below it, call
   navigate to the same url once more so the pane re-measures, then take one more
   screenshot.

4. Reply with ONE short line (e.g. "Board's up.") and STOP. Do nothing beyond
   steps 1-3 — no page reading, no further navigation.
