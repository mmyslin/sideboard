# Sideboard — working notes for Claude

Sideboard's own roadmap lives in **GitHub Issues** (`mmyslin/sideboard`). The project
is **GitHub-only** — there is no `roadmap.json` / local-file mode.

- **Manage roadmap items via `gh`** — `gh issue create` / `edit` / `close` /
  `reopen`. Swimlane (backlog vs in_progress) + card order live in
  `.sideboard/meta.json` (committed sidecar); **`done` = a closed issue**; a card's
  `#N` is its GitHub issue number. The sidecar is reconciled automatically by the
  router from the issues + your drag/reorder — don't hand-edit it.
- **Run the board:** `./sideboard-up.sh` — starts the **router**
  (`sideboard_router.py`) on :7777, which follows the *active* project and serves
  its board. Then open the pane once per project (or use `/roadmap`).
- **Multi-project / auto-follow (#35):** one router serves ALL projects. A global
  Claude Code hook (`sideboard-active.sh`, on SessionStart + UserPromptSubmit)
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
- Design + phases: `docs/github-sync-design.md` (#15). Distribution plan: ship as
  a Claude Code plugin (#12). Naming decision: #39.

The global `sideboard` skill (`skill/SKILL.md`) documents this same GitHub-only
model — this file is just the repo-specific pointer.
