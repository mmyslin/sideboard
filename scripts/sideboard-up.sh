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
STATE_DIR="$HOME/.claude"
mkdir -p "$STATE_DIR" 2>/dev/null                       # log/stamps live here (#91)
# Print the board URL WITH the auth token: since reads are token-gated (#111), a
# bare token-less URL renders only a read-only, data-less shell — so handing the
# user that URL is handing them a broken board (#140). The board reads the token
# from ?token=; it's the user's own secret shown in their own terminal.
_tok="$(cat "$STATE_DIR/sideboard-token" 2>/dev/null)"
url="http://127.0.0.1:$PORT/roadmap-board.html"
[ -n "$_tok" ] && url="$url?token=$_tok"
cd "$(dirname "$0")" || exit 1

health()    { curl -sf -m 1 "http://127.0.0.1:$PORT/healthz" 2>/dev/null; }
is_router() { printf '%s' "$1" | grep -q '"router": *true'; }
access_ok() { printf '%s' "$1" | grep -q '"access_ok": *true'; }

# PIDs listening on $PORT (lsof → ss → fuser; "NOTOOL" if none exist, #118).
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
is_our_router_pid() {   # only OUR router is safe to SIGKILL (#110)
  case "$(ps -o command= -p "$1" 2>/dev/null)" in
    *sideboard_router.py*|*vibemap_router.py*|*github_companion.py*) return 0 ;;
    *) return 1 ;;
  esac
}

launch() {
  date +%s >"$STATE_DIR/sideboard-relaunch.stamp"
  local pids foreign="" pid
  pids=$(port_listener_pids)
  if [ "$pids" = "NOTOOL" ]; then
    echo "no lsof/ss/fuser to find the port owner — starting router blind" >&2
    pids=""
  fi
  for pid in $pids; do
    if is_our_router_pid "$pid"; then kill -9 "$pid" 2>/dev/null   # our own stale/wedged router (#92)
    else foreign="$foreign $pid"; fi
  done
  if [ -n "$foreign" ]; then
    # A non-Sideboard process holds the port — never kill it (#110). This IS the
    # #35 "wrong server" case for OUR own legacy routers (matched above and killed);
    # anything else is the user's and stays untouched.
    echo "port $PORT is held by a non-Sideboard process (pid$foreign); refusing to kill it. Set SIDEBOARD_PORT to run on another port." >&2
    return 1
  fi
  nohup python3 sideboard_router.py >>"$STATE_DIR/sideboard-router.log" 2>&1 &   # append (#105)
  echo $! >"$STATE_DIR/sideboard-router.pid"   # record our router's PID for ps-independent reclaim (#151)
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
  # Honor launch()'s exit status: a foreign process on the port makes it refuse
  # (return 1) rather than kill, and printing "started -> url" then would be a lie —
  # the router isn't up and the board would 403/empty (#153).
  if launch; then
    is_router "$(health)" && echo "started -> $url" || echo "started (warming up) -> $url"
  else
    echo "could NOT start: port $PORT is held by a non-Sideboard process (see $STATE_DIR/sideboard-router.log). Set SIDEBOARD_PORT to run on another port." >&2
    exit 1
  fi
fi
