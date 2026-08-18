#!/usr/bin/env bash
# Sideboard activity hook — tell the router which project is active.
#
# Wired to Claude Code's SessionStart + UserPromptSubmit hooks. Reads the hook
# JSON on stdin, extracts the session TITLE (the only reliable project signal in
# this setup — cwd is always $HOME), and POSTs it to the router so the pinned
# preview pane follows whatever project you're working in. Fire-and-forget;
# boots the router if it's down. Always exits 0 so it never FAILS the prompt;
# latency is bounded (a readiness wait plus short-timeout curls) and hard-capped
# by the `timeout` set on the hook in hooks.json (#119).
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

# PIDs listening on $PORT, one per line. Tries lsof, then ss, then fuser so a box
# without lsof (slim Linux/Docker) can still reclaim the port instead of looping
# forever on EADDRINUSE (#118). Echoes "NOTOOL" when none of the three exist.
port_listener_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null
  elif command -v ss >/dev/null 2>&1; then
    ss -H -ltnp "sport = :$PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
  elif command -v fuser >/dev/null 2>&1; then
    fuser "$PORT/tcp" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$'
  else
    echo NOTOOL
  fi
}

# Is PID $1 one of OUR router processes? Guards the kill so we never SIGKILL an
# unrelated service that merely happens to hold the port (#110).
is_our_router_pid() {
  case "$(ps -o command= -p "$1" 2>/dev/null)" in
    *sideboard_router.py*|*vibemap_router.py*|*github_companion.py*) return 0 ;;
    *) return 1 ;;
  esac
}

launch() {
  date +%s >"$STATE_DIR/sideboard-relaunch.stamp"   # advance the throttle for EVERY outcome, incl. the foreign-port refusal below
  local pids foreign="" pid
  pids=$(port_listener_pids)
  if [ "$pids" = "NOTOOL" ]; then
    echo "[sideboard] no lsof/ss/fuser available to find the port owner; starting router blind (a bind clash will show below)" >>"$STATE_DIR/sideboard-router.log"
    pids=""
  fi
  for pid in $pids; do
    if is_our_router_pid "$pid"; then
      kill -9 "$pid" 2>/dev/null           # our own stale/wedged router — safe to reclaim (#92)
    else
      foreign="$foreign $pid"
    fi
  done
  if [ -n "$foreign" ]; then
    # A non-Sideboard process holds the port. NEVER kill it (the old code SIGKILLed
    # whatever was listening on a failed healthz, taking out unrelated services on
    # 7777, #110). Back off and tell the user how to move us instead.
    echo "[sideboard] port $PORT is held by a non-Sideboard process (pid$foreign); refusing to kill it. Set SIDEBOARD_PORT to run Sideboard on another port." >>"$STATE_DIR/sideboard-router.log"
    return 1
  fi
  nohup python3 "$HERE/sideboard_router.py" >>"$STATE_DIR/sideboard-router.log" 2>&1 &   # append: racing launches must not truncate each other's log (#105)
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do   # wait for readiness (~1.5s cap) instead of a flat sleep 1 (#119)
    healthz && break
    sleep 0.1
  done
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

# Router is up (healthz) but /active still got nothing back: almost always a
# missing/empty auth token, which makes the hook silently useless — the board
# never follows the active project and nothing says why (#129). Diagnose it once
# per 60s (its own stamp) rather than on every prompt.
if [ -z "$resp" ] && healthz && [ ! -s "$STATE_DIR/sideboard-token" ]; then
  last=$(cat "$STATE_DIR/sideboard-token-warn.stamp" 2>/dev/null || echo 0)
  if [ "$(( $(date +%s) - last ))" -ge 60 ]; then
    date +%s >"$STATE_DIR/sideboard-token-warn.stamp"
    echo "[sideboard] router is up but $STATE_DIR/sideboard-token is missing/empty, so /active is rejected (403) and the board can't follow your project. Restart the router (sideboard-up.sh) to regenerate it." >>"$STATE_DIR/sideboard-router.log"
  fi
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
