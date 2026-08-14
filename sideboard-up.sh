#!/usr/bin/env bash
# Ensure the Sideboard ROUTER is serving the board on :7777; print its URL.
#
# The router follows the ACTIVE project (set by the SessionStart/UserPromptSubmit
# hook -> sideboard-active.sh), so the pinned pane follows whatever project you're
# in. Safe to run repeatedly; started detached. If :7777 is held by something
# that ISN'T the router (a wedged process, or a stale vibemap_router.py /
# github_companion.py left over from before the rename/retirement), reclaim the
# port and start the router — this is the #35 "wrong server" fix.
url="http://127.0.0.1:7777/roadmap-board.html"
cd "$(dirname "$0")" || exit 1

is_router() { curl -sf -m 1 http://127.0.0.1:7777/healthz 2>/dev/null | grep -q '"router": *true'; }

if is_router; then
  echo "already up -> $url"
else
  # reclaim by process name — NOT `lsof -ti:7777 | kill`, which also matches the
  # Claude app's client socket on :7777 and would kill/disrupt the app itself.
  pkill -9 -f 'sideboard_router.py|vibemap_router.py|github_companion.py' 2>/dev/null
  nohup python3 sideboard_router.py >/tmp/sideboard-router.log 2>&1 &
  for _ in $(seq 1 40); do is_router && break; sleep 0.05; done   # return as soon as ready (~2s cap), not a fixed 3s
  is_router && echo "started -> $url" || echo "started (warming up) -> $url"
fi
