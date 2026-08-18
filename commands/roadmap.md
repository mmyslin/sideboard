---
description: Open the Sideboard roadmap board in the preview pane
model: haiku
effort: low
---
Open my Sideboard roadmap board. The router is already running on :7777.

1. Call navigate with url `http://127.0.0.1:7777/roadmap-board.html` to reuse the
   existing pane tab. ONLY if navigate errors that no preview/pane is open, call
   preview_start once with that same url.

2. DEV-MODE LIVENESS CHECK (temporary — remove once the pane stops wedging):
   take ONE screenshot to confirm the board actually rendered. It's healthy if
   you can see the PROJECT header and the Backlog / In Progress / Done columns
   with cards. If instead the pane is blank, OR the board is crushed into a short
   strip at the top with empty space below it (a collapsed-viewport glitch), call
   navigate to the same url ONCE more to make the pane re-measure, then take one
   more screenshot.

3. Reply with ONE short line (e.g. "Board's up.") and STOP. Do nothing beyond
   steps 1-2 — no page reading, no further navigation.
