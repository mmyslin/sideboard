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
- **Run the board:** `python3 github_companion.py` (serves :7777 + syncs every
  ~45s). Not `python -m http.server`.
- Design + phases: `docs/github-sync-design.md` (#15). Board-initiated writes
  (Edit / move / add) are still to come — Phases 2–3; today the board is
  read-only over GitHub.

This overrides the global `vibemap` skill's "edit roadmap.json directly"
guidance **for this repo only** (other projects still use local-file mode).
