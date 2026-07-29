#!/usr/bin/env bash
# Ensure the VibeMap GitHub companion is serving the board; print its URL.
# Safe to run repeatedly. Started detached so it survives the terminal closing.
url="http://127.0.0.1:7777/roadmap-board.html"
cd "$(dirname "$0")" || exit 1
if curl -sf -o /dev/null --max-time 1 "$url" 2>/dev/null; then
  echo "already up -> $url"
else
  nohup python3 github_companion.py >/tmp/vibemap-companion.log 2>&1 &
  sleep 2
  echo "started -> $url"
fi
