#!/usr/bin/env bash
# Ensure the VibeMap ROUTER is serving the board on :7777; print its URL.
#
# The router follows the ACTIVE project (set by the SessionStart/UserPromptSubmit
# hook -> vibemap-active.sh), so the pinned pane follows whatever project you're
# in. Safe to run repeatedly; started detached. If :7777 is held by something
# that ISN'T the router (a stale single-project companion, or a wedged process),
# reclaim the port and start the router — this is the #35 "wrong server" fix.
url="http://127.0.0.1:7777/roadmap-board.html"
cd "$(dirname "$0")" || exit 1

is_router() { curl -sf -m 1 http://127.0.0.1:7777/healthz 2>/dev/null | grep -q '"router": *true'; }

if is_router; then
  echo "already up -> $url"
else
  # reclaim by process name — NOT `lsof -ti:7777 | kill`, which also matches the
  # Claude app's client socket on :7777 and would kill/disrupt the app itself.
  pkill -9 -f 'vibemap_router.py|github_companion.py' 2>/dev/null
  sleep 1
  nohup python3 vibemap_router.py >/tmp/vibemap-router.log 2>&1 &
  sleep 2
  is_router && echo "started -> $url" || echo "started (warming up) -> $url"
fi
