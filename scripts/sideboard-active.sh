#!/usr/bin/env bash
# Sideboard activity hook — tell the router which project is active.
#
# Wired to Claude Code's SessionStart + UserPromptSubmit hooks. Reads the hook
# JSON on stdin, extracts the session TITLE (the only reliable project signal in
# this setup — cwd is always $HOME), and POSTs it to the router so the pinned
# preview pane follows whatever project you're working in. Fire-and-forget;
# boots the router if it's down. Never blocks the prompt (always exits 0).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # router lives next to this script
PORT="${SIDEBOARD_PORT:-7777}"                          # keep in step with the router (#102)
STATE_DIR="$HOME/.claude"
mkdir -p "$STATE_DIR" 2>/dev/null   # log/stamps/token live here — without it the rate limit
                                    # silently dies and every prompt relaunches (#91)
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
# Writes require the per-install secret the router keeps in ~/.claude (#89).
post() {
  curl -sf -m 1 -X POST "http://127.0.0.1:$PORT/active" \
    -H 'Content-Type: application/json' \
    -H "X-Sideboard-Token: $(cat "$STATE_DIR/sideboard-token" 2>/dev/null)" \
    -d "$body" 2>/dev/null
}
healthz() { curl -sf -m 1 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; }
launch() {
  # Reclaim the port by killing exactly the process LISTENING on it — never a
  # name-pattern pkill, which SIGKILLed editors/greps whose argv merely mentioned
  # the filename and missed routers under a versioned interpreter (#92). The
  # -sTCP:LISTEN filter is what makes this safe: client sockets (e.g. the Claude
  # app's own connection to :7777) never match.
  pids=$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null)
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null
  nohup python3 "$HERE/sideboard_router.py" >>"$STATE_DIR/sideboard-router.log" 2>&1 &   # append: racing launches must not truncate each other's log (#105)
  date +%s >"$STATE_DIR/sideboard-relaunch.stamp"
  sleep 1
}

# Ensure the board server is up BEFORE the title guard, so a titleless session
# (e.g. SessionStart source=startup, which carries no session_title) still boots
# it — otherwise the "hook starts the board for you" promise was conditional (#65).
# Rate-limited to one relaunch/60s.
if ! healthz; then
  last=$(cat "$STATE_DIR/sideboard-relaunch.stamp" 2>/dev/null || echo 0)
  [ "$(( $(date +%s) - last ))" -ge 60 ] && launch
fi

# No title (e.g. SessionStart source=startup) → router is up, but nothing to route.
[ -z "$body" ] && exit 0

resp="$(post)"
# /active failed. Only treat that as "router down" if healthz ALSO fails — a
# router that answers healthz but is slow on /active (first-run TCC dialog,
# stalled filesystem) is alive and must not be SIGKILLed (#93). Rate-limited to
# one relaunch/60s: an unthrottled loop would pkill -9 + restart on EVERY
# prompt — a storm that can itself corrupt sidecars (#60).
if [ -z "$resp" ] && ! healthz; then
  last=$(cat "$STATE_DIR/sideboard-relaunch.stamp" 2>/dev/null || echo 0)
  [ "$(( $(date +%s) - last ))" -ge 60 ] && { launch; resp="$(post)"; }
fi

# Self-heal (#46): a router that's up but can't read ~/Documents (macOS TCC denied
# the process on a bad launch) serves broken boards. Relaunch it from THIS hook
# context — which normally holds the Files/Documents grant — so the user never has
# to restart it by hand. Uses its OWN stamp: the boot-path launch above must not
# throttle the first heal for 60s (#109). Still rate-limited so a persistent
# denial (e.g. Claude itself lacking the grant) can't relaunch on every prompt.
if printf '%s' "$resp" | grep -q '"ok": *true' \
   && ! printf '%s' "$resp" | grep -q '"access_ok": *true'; then
  last=$(cat "$STATE_DIR/sideboard-heal.stamp" 2>/dev/null || echo 0)
  if [ "$(( $(date +%s) - last ))" -ge 60 ]; then
    date +%s >"$STATE_DIR/sideboard-heal.stamp"
    launch
    post >/dev/null
  fi
fi
exit 0
