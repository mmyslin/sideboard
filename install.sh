#!/usr/bin/env bash
# Install Sideboard for Claude Code: the board renderer, the multi-project router,
# the /sideboard skill, and the global activity hook that makes the preview pane
# follow whatever project you're working in (#35, #36). Re-run any time to update.
#
# LEGACY installer. The supported path is now the Claude Code plugin (#12):
#   /plugin marketplace add mmyslin/sideboard
#   /plugin install sideboard@sideboard
# This script remains for users not on the plugin flow; it copies the same files
# out of the plugin layout (skills/, scripts/) into ~/.claude/skills/sideboard/.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/sideboard"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

# One-time cleanup: remove the pre-rename VibeMap install so it doesn't linger
# beside the new one (the stale hook is also stripped from settings.json below).
rm -rf "${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/vibemap"

mkdir -p "$DEST"
cp "$SRC/skills/sideboard/SKILL.md"   "$DEST/SKILL.md"
cp "$SRC/roadmap-board.html"          "$DEST/roadmap-board.html"
cp "$SRC/scripts/sideboard_router.py" "$DEST/sideboard_router.py"
cp "$SRC/scripts/sideboard-active.sh" "$DEST/sideboard-active.sh"
cp "$SRC/scripts/sideboard-up.sh"     "$DEST/sideboard-up.sh"
chmod +x "$DEST/sideboard-active.sh" "$DEST/sideboard-up.sh" "$DEST/sideboard_router.py"
echo "✅ Installed Sideboard files to: $DEST"

# Merge the SessionStart + UserPromptSubmit hooks into settings.json, without
# clobbering existing keys/hooks. Idempotent: re-running replaces only Sideboard's
# own hook groups (so a changed install path is picked up cleanly).
HOOK_CMD="$DEST/sideboard-active.sh"
[ -f "$SETTINGS" ] && cp "$SETTINGS" "$SETTINGS.sideboard.bak"
python3 - "$SETTINGS" "$HOOK_CMD" <<'PY'
import json, os, sys
settings_path, cmd = sys.argv[1], sys.argv[2]
try:
    with open(settings_path) as f:
        s = json.load(f)
except FileNotFoundError:
    s = {}
except Exception as e:
    sys.exit(f"ERROR: {settings_path} is not valid JSON; leaving it untouched ({e}).")

def is_ours(group):
    # matches our current hook AND the legacy vibemap-active.sh, so re-running
    # after the rename cleanly replaces the old group instead of duplicating it.
    hs = group.get("hooks", [])
    return bool(hs) and all(
        ("sideboard-active.sh" in h.get("command", "") or "vibemap-active.sh" in h.get("command", ""))
        for h in hs)

hooks = s.setdefault("hooks", {})
for event in ("SessionStart", "UserPromptSubmit"):
    groups = [g for g in hooks.get(event, []) if not is_ours(g)]   # drop our prior group(s)
    # Quote the path (like the plugin's hooks.json does): the command is run by a
    # shell, and an unquoted $HOME/CLAUDE_SKILLS_DIR with a space word-splits (#103).
    groups.append({"hooks": [{"type": "command", "command": f'"{cmd}"'}]})
    hooks[event] = groups

os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w") as f:
    json.dump(s, f, indent=2)
    f.write("\n")
print(f"✅ Wired SessionStart + UserPromptSubmit hooks in: {settings_path}")
PY

cat <<EOF

Next:
  • Start a NEW Claude Code session so the updated settings load.
  • In each project, open the board once — point the preview pane at
    http://127.0.0.1:7777/roadmap-board.html (e.g. run \`$DEST/sideboard-up.sh\`
    first, or use the /roadmap command if you have it).
  • Switch projects and send a message; each project's pane follows along.
  • Title→directory map lives in ~/.claude/sideboard-projects.json (auto-seeded
    from ~/Documents/Projects; edit it to override or set SIDEBOARD_PROJECTS_ROOT).
EOF
