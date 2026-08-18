#!/usr/bin/env bash
# Sideboard activity hook — tell the router which project is active.
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

# POST the active project; echo the JSON reply (empty if the router is unreachable).
post() {
  curl -sf -m 1 -X POST http://127.0.0.1:7777/active \
    -H 'Content-Type: application/json' -d "$body" 2>/dev/null
}
launch() {
  # reclaim by process name (never `lsof -ti:7777 | kill` — that also matches the
  # Claude app's client socket on :7777), start detached, and stamp the time.
  pkill -9 -f 'sideboard_router.py|vibemap_router.py|github_companion.py' 2>/dev/null
  nohup python3 "$HERE/sideboard_router.py" >/tmp/sideboard-router.log 2>&1 &
  date +%s >/tmp/sideboard-relaunch.stamp
  sleep 1
}

# Ensure the board server is up BEFORE the title guard, so a titleless session
# (e.g. SessionStart source=startup, which carries no session_title) still boots
# it — otherwise the "hook starts the board for you" promise was conditional (#65).
# Rate-limited to one relaunch/60s.
if ! curl -sf -m 1 http://127.0.0.1:7777/healthz >/dev/null 2>&1; then
  last=$(cat /tmp/sideboard-relaunch.stamp 2>/dev/null || echo 0)
  [ "$(( $(date +%s) - last ))" -ge 60 ] && launch
fi

# No title (e.g. SessionStart source=startup) → router is up, but nothing to route.
[ -z "$body" ] && exit 0

resp="$(post)"
# Router unreachable -> start it, but rate-limit to one relaunch/60s. If /active keeps
# failing (e.g. a persistent 500), an unthrottled relaunch would pkill -9 + restart on
# EVERY prompt — a storm that can itself corrupt sidecars (#60).
if [ -z "$resp" ]; then
  last=$(cat /tmp/sideboard-relaunch.stamp 2>/dev/null || echo 0)
  [ "$(( $(date +%s) - last ))" -ge 60 ] && { launch; resp="$(post)"; }
fi

# Self-heal (#46): a router that's up but can't read ~/Documents (macOS TCC denied
# the process on a bad launch) serves broken boards. Relaunch it from THIS hook
# context — which normally holds the Files/Documents grant — so the user never has
# to restart it by hand. Rate-limited to one relaunch/60s so a persistent denial
# (e.g. Claude itself lacking the grant) can't relaunch on every prompt.
if printf '%s' "$resp" | grep -q '"ok": *true' \
   && ! printf '%s' "$resp" | grep -q '"access_ok": *true'; then
  last=$(cat /tmp/sideboard-relaunch.stamp 2>/dev/null || echo 0)
  [ "$(( $(date +%s) - last ))" -ge 60 ] && { launch; post >/dev/null; }
fi
exit 0
