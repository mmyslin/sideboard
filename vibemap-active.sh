#!/usr/bin/env bash
# VibeMap activity hook — tell the router which project is active.
#
# Wired to Claude Code's SessionStart + UserPromptSubmit hooks. Reads the hook
# JSON on stdin, extracts the session TITLE (the only reliable project signal in
# this setup — cwd is always $HOME), and POSTs it to the router so the pinned
# preview pane follows whatever project you're working in. Fire-and-forget;
# boots the router if it's down. Never blocks the prompt (always exits 0).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # router lives next to this script
payload=$(cat)

body=$(printf '%s' "$payload" | python3 -c "
import sys, json
try:
    t = (json.load(sys.stdin).get('session_title') or '').strip()
except Exception:
    t = ''
print(json.dumps({'session_title': t}) if t else '')
" 2>/dev/null)

# No title (e.g. SessionStart source=startup) → nothing to route.
[ -z "$body" ] && exit 0

post() {
  curl -sf -m 1 -X POST http://127.0.0.1:7777/active \
    -H 'Content-Type: application/json' -d "$body" >/dev/null 2>&1
}

if ! post; then
  nohup python3 "$HERE/vibemap_router.py" >/tmp/vibemap-router.log 2>&1 &
  sleep 1
  post
fi
exit 0
