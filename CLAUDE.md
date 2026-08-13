# VibeMap — working notes for Claude

This project **dogfoods "github mode"**: its roadmap lives in **GitHub Issues**
(`mmyslin/vibemap`), not in `roadmap.json`.

- **Manage roadmap items via `gh`** — `gh issue create` / `edit` / `close` /
  `reopen`. Do **NOT** edit `roadmap.json`: it's a generated artifact
  (gitignored), rebuilt by `github_companion.py` from the issues + the
  `.vibemap/meta.json` sidecar. Editing it does nothing durable.
- **Swimlane (backlog vs in_progress) + card order** live in
  `.vibemap/meta.json` (committed). **`done` = a closed issue.**
- **A card's `#N` is its GitHub issue number.**
- **Run the board:** `./vibemap-up.sh` — starts the **router**
  (`vibemap_router.py`) on :7777, which follows the *active* project and serves
  its board. (`github_companion.py` is the older single-project server; the
  router supersedes it for day-to-day use.) Then open the pane once per project.
- **Multi-project / auto-follow (#35):** one router serves ALL projects. A global
  Claude Code hook (`vibemap-active.sh`, on SessionStart + UserPromptSubmit)
  POSTs the session TITLE to the router, which maps title→project dir
  (`~/.claude/vibemap-projects.json`, token-matched, editable) and switches the
  served board. cwd is useless here (always $HOME) — title is the only signal.
  The preview pane is per-session, so open it once per project with `/roadmap`;
  thereafter switching projects (send a message) makes each project's pane show
  its own roadmap.
- Design + phases: `docs/github-sync-design.md` (#15). Board-initiated writes
  (Edit / move / add) are still to come — Phases 2–3; today the board is
  read-only over GitHub.

This overrides the global `vibemap` skill's "edit roadmap.json directly"
guidance **for this repo only** (other projects still use local-file mode).
