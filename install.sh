#!/usr/bin/env bash
# Install the vibemap skill for Claude Code.
# Copies the skill + board into your Claude Code skills directory so `/vibemap`
# is available in every project. Re-run any time to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/vibemap"

mkdir -p "$DEST"
cp "$SRC/skill/SKILL.md"        "$DEST/SKILL.md"
cp "$SRC/roadmap-board.html"    "$DEST/roadmap-board.html"

echo "✅ Installed vibemap skill to: $DEST"
echo "   Start a new Claude Code session, then run /vibemap in any project."
