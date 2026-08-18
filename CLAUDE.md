# Sideboard — working notes for Claude

Sideboard's own roadmap lives in **GitHub Issues** (`mmyslin/sideboard`). The project
is **GitHub-only** — there is no `roadmap.json` / local-file mode.

- **Manage roadmap items via `gh`** — `gh issue create` / `edit` / `close` /
  `reopen`. Swimlane (backlog vs in_progress) + card order live in
  `.sideboard/meta.json` (committed sidecar); **`done` = a closed issue**; a card's
  `#N` is its GitHub issue number. The sidecar is reconciled automatically by the
  router from the issues + your drag/reorder — don't hand-edit it.
- **Sequences** — ordered dependency chains of ≥2 issues (in `.sideboard/meta.json`),
  managed via the `/roadmap-sequence` command + the router's `/api/seq/*`. Honor them
  when working: starting a sequenced issue with an unfinished predecessor → check in
  first; closing one → suggest the next. See `skills/sideboard/SKILL.md` → "Acting on
  a sequenced issue".
- **Repo layout is the plugin layout (#12):** `commands/` (the `sideboard:`
  slash commands), `skills/sideboard/SKILL.md`, `scripts/` (router + shell
  scripts), `hooks/hooks.json`, and `.claude-plugin/{plugin,marketplace}.json`.
  `install.sh` is the legacy installer; it copies out of `skills/`+`scripts/`.
- **Releasing (version-bump convention):** once listed in the community
  marketplace, Anthropic's CI auto-advances the catalog's commit-SHA pin on every
  push — but users only *receive* an update when **`version` in
  `.claude-plugin/plugin.json` changes**. So push freely (docs, refactors, WIP);
  **bump `version` (semver) only when you want users to get the change** — that
  bump is the deliberate "ship it" lever. Keep the marketplace entry free of a
  `version` field so `plugin.json` stays the single source of truth. No
  re-submission is needed for updates (whether each push is re-screened is
  undocumented).
- **Run the board:** `scripts/sideboard-up.sh` — starts the **router**
  (`scripts/sideboard_router.py`) on :7777, which follows the *active* project and
  serves its board. Then open the pane once per project (or use `/sideboard:roadmap`).
  Under the plugin the `SessionStart` hook launches it for you.
- **Multi-project / auto-follow (#35):** one router serves ALL projects. A global
  Claude Code hook (`scripts/sideboard-active.sh`, on SessionStart + UserPromptSubmit)
  POSTs the session TITLE to the router, which maps title→project dir
  (`~/.claude/sideboard-projects.json`, token-matched, editable) and switches the
  served board. cwd is useless here (always $HOME) — title is the only signal.
  The preview pane is per-session, so open it once per project with `/roadmap`;
  thereafter switching projects (send a message) makes each project's pane show
  its own roadmap.
- **Discovery** keys off `.sideboard/meta.json`: a project is only picked up once
  that sidecar exists. Bootstrap a new repo with
  `mkdir -p .sideboard && printf '{"schema": 1}\n' > .sideboard/meta.json` (commit
  it); the router reconciles it from the issues on first sync.
- Design + phases: `docs/github-sync-design.md` (#15). Distribution: shipped as a
  Claude Code plugin (#12) — community-marketplace submission is the remaining
  discoverability step. Naming decision: #39.

The global `sideboard` skill (`skills/sideboard/SKILL.md`) documents this same
GitHub-only model — this file is just the repo-specific pointer.
