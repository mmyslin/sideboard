#!/usr/bin/env bash
# Install VibeMap for Claude Code: the board renderer, the multi-project router,
# the /vibemap skill, and the global activity hook that makes the preview pane
# follow whatever project you're working in (#35, #36). Re-run any time to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/vibemap"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

mkdir -p "$DEST"
cp "$SRC/skill/SKILL.md"       "$DEST/SKILL.md"
cp "$SRC/roadmap-board.html"   "$DEST/roadmap-board.html"
cp "$SRC/vibemap_router.py"    "$DEST/vibemap_router.py"
cp "$SRC/vibemap-active.sh"    "$DEST/vibemap-active.sh"
cp "$SRC/vibemap-up.sh"        "$DEST/vibemap-up.sh"
chmod +x "$DEST/vibemap-active.sh" "$DEST/vibemap-up.sh" "$DEST/vibemap_router.py"
echo "✅ Installed VibeMap files to: $DEST"

# Merge the SessionStart + UserPromptSubmit hooks into settings.json, without
# clobbering existing keys/hooks. Idempotent: re-running replaces only VibeMap's
# own hook groups (so a changed install path is picked up cleanly).
HOOK_CMD="$DEST/vibemap-active.sh"
[ -f "$SETTINGS" ] && cp "$SETTINGS" "$SETTINGS.vibemap.bak"
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
    hs = group.get("hooks", [])
    return bool(hs) and all("vibemap-active.sh" in h.get("command", "") for h in hs)

hooks = s.setdefault("hooks", {})
for event in ("SessionStart", "UserPromptSubmit"):
    groups = [g for g in hooks.get(event, []) if not is_ours(g)]   # drop our prior group(s)
    groups.append({"hooks": [{"type": "command", "command": cmd}]})
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
    http://127.0.0.1:7777/roadmap-board.html (e.g. run \`$DEST/vibemap-up.sh\`
    first, or use the /roadmap command if you have it).
  • Switch projects and send a message; each project's pane follows along.
  • Title→directory map lives in ~/.claude/vibemap-projects.json (auto-seeded
    from ~/Documents/Projects; edit it to override or set VIBEMAP_PROJECTS_ROOT).
EOF
