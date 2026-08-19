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
# Fingerprint it by a file ONLY our old install shipped — its router script. The
# earlier guard also accepted SKILL.md, but EVERY skill dir has a SKILL.md, so an
# unrelated ~/.claude/skills/vibemap the user happens to keep would have matched
# and been rm -rf'd (#144). Requiring the router script can't false-positive.
OLD_VIBEMAP="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/vibemap"
if [ -d "$OLD_VIBEMAP" ] && { [ -e "$OLD_VIBEMAP/vibemap_router.py" ] || [ -e "$OLD_VIBEMAP/github_companion.py" ]; }; then
  rm -rf "$OLD_VIBEMAP"
fi

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
    # Carry the same timeout: 8 the plugin's hooks.json sets, or a legacy install's
    # hook has no latency hard-cap at all — voiding the #119 guarantee (#150).
    groups.append({"hooks": [{"type": "command", "command": f'"{cmd}"', "timeout": 8}]})
    hooks[event] = groups

os.makedirs(os.path.dirname(settings_path), exist_ok=True)
# Write atomically: settings.json is the user's whole Claude Code config, and a
# crash/interrupt mid-write would leave it truncated — disabling every setting in
# it, not just ours. Write a temp beside it and os.replace (a .sideboard.bak was
# already taken above). (#128)
tmp = settings_path + ".sideboard.tmp"
with open(tmp, "w") as f:
    json.dump(s, f, indent=2)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, settings_path)
print(f"✅ Wired SessionStart + UserPromptSubmit hooks in: {settings_path}")
PY

cat <<EOF

Next:
  • Start a NEW Claude Code session so the updated settings load.
  • In each project, open the board once. Reads are token-gated, so the board URL
    must carry the auth token — a bare URL renders an empty, read-only board. Run
    \`$DEST/sideboard-up.sh\`; it prints the correct
    http://127.0.0.1:7777/roadmap-board.html?token=... URL — point the preview
    pane at THAT. (Or build it by hand:
    http://127.0.0.1:7777/roadmap-board.html?token=\$(cat ~/.claude/sideboard-token).)
  • Switch projects and send a message; each project's pane follows along.
  • Title→directory map lives in ~/.claude/sideboard-projects.json (auto-seeded
    from ~/Documents/Projects; edit it to override or set SIDEBOARD_PROJECTS_ROOT).
EOF
