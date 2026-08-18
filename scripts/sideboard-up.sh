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

health()    { curl -sf -m 1 http://127.0.0.1:7777/healthz 2>/dev/null; }
is_router() { printf '%s' "$1" | grep -q '"router": *true'; }
access_ok() { printf '%s' "$1" | grep -q '"access_ok": *true'; }
launch() {
  # reclaim by process name — NOT `lsof -ti:7777 | kill`, which also matches the
  # Claude app's client socket on :7777 and would kill/disrupt the app itself.
  # Anchor to the interpreter so a bare filename in an editor/pager argv (e.g.
  # `vim sideboard_router.py`) isn't SIGKILLed too (#66).
  pkill -9 -f 'python3? .*(sideboard_router|vibemap_router|github_companion)\.py' 2>/dev/null
  nohup python3 sideboard_router.py >"$HOME/.claude/sideboard-router.log" 2>&1 &
  date +%s >"$HOME/.claude/sideboard-relaunch.stamp"
  for _ in $(seq 1 40); do is_router "$(health)" && break; sleep 0.05; done   # ready within ~2s
}

h="$(health)"
if is_router "$h"; then
  if access_ok "$h"; then
    echo "already up -> $url"
  else
    # Up, but macOS is blocking its ~/Documents access (#46). Relaunch from this
    # context, which normally holds the grant. Rate-limited to avoid a loop.
    last=$(cat "$HOME/.claude/sideboard-relaunch.stamp" 2>/dev/null || echo 0)
    if [ "$(( $(date +%s) - last ))" -ge 60 ]; then
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
