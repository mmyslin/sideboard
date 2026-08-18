#!/usr/bin/env bash
# Ensure the Sideboard ROUTER is serving the board; print its URL.
#
# The router follows the ACTIVE project (set by the SessionStart/UserPromptSubmit
# hook -> sideboard-active.sh), so the pinned pane follows whatever project you're
# in. Safe to run repeatedly; started detached. If the port is held by something
# that ISN'T the router (a wedged process, or a stale vibemap_router.py /
# github_companion.py left over from before the rename/retirement), reclaim the
# port and start the router — this is the #35 "wrong server" fix.
PORT="${SIDEBOARD_PORT:-7777}"                          # keep in step with the router (#102)
url="http://127.0.0.1:$PORT/roadmap-board.html"
STATE_DIR="$HOME/.claude"
mkdir -p "$STATE_DIR" 2>/dev/null                       # log/stamps live here (#91)
cd "$(dirname "$0")" || exit 1

health()    { curl -sf -m 1 "http://127.0.0.1:$PORT/healthz" 2>/dev/null; }
is_router() { printf '%s' "$1" | grep -q '"router": *true'; }
access_ok() { printf '%s' "$1" | grep -q '"access_ok": *true'; }
launch() {
  # Reclaim by killing exactly the LISTENER on the port — the -sTCP:LISTEN filter
  # never matches client sockets (e.g. the Claude app's connection), and unlike a
  # name-pattern pkill it can't hit editors/greps or miss a router started under a
  # versioned interpreter (#92).
  pids=$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null)
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null
  nohup python3 sideboard_router.py >>"$STATE_DIR/sideboard-router.log" 2>&1 &   # append (#105)
  date +%s >"$STATE_DIR/sideboard-relaunch.stamp"
  for _ in $(seq 1 40); do is_router "$(health)" && break; sleep 0.05; done   # ready within ~2s
}

h="$(health)"
if is_router "$h"; then
  if access_ok "$h"; then
    echo "already up -> $url"
  else
    # Up, but macOS is blocking its ~/Documents access (#46). Relaunch from this
    # context, which normally holds the grant. Rate-limited to avoid a loop.
    last=$(cat "$STATE_DIR/sideboard-heal.stamp" 2>/dev/null || echo 0)
    if [ "$(( $(date +%s) - last ))" -ge 60 ]; then
      date +%s >"$STATE_DIR/sideboard-heal.stamp"
      echo "router up but has no ~/Documents access — relaunching (#46)"
      launch
      access_ok "$(health)" && echo "recovered -> $url" \
        || echo "still no access — restart Claude, or grant it Files & Folders access -> $url"
    else
      echo "already up (no access; relaunched recently) -> $url"
    fi
  fi
else
  launch
  is_router "$(health)" && echo "started -> $url" || echo "started (warming up) -> $url"
fi
