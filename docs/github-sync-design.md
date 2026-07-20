# VibeMap ↔ GitHub Issues — design (#15)

## Decision

GitHub Issues are the **single source of truth** for roadmap items. A small local
**companion** process syncs them into the file the board already polls, and takes
writes back to GitHub. Board presentation that Issues can't express (swimlane
split, manual order) lives in a local **sidecar**. Not pluggable yet — GitHub
mode only; a repo is required (that's fine / desirable).

## What lives where

| Concept | Home | Notes |
|---|---|---|
| Item exists / title / description | **GitHub issue** (`title`, `body`) | canonical |
| Done vs not-done | **GitHub open/closed** | `done` column = closed issue |
| Backlog vs In Progress (for open issues) | **sidecar** | GitHub has no native "status" without Projects |
| Manual order (rank) | **sidecar** | Issues have no manual order |
| Card number `#N` | **GitHub issue number** | drop the old `seq` counter; refs = issue numbers |

Keeping `done` = closed (not in the sidecar) means each concept lives in exactly
one place — no dual-sourced "done".

### Sidecar — `.vibemap/meta.json` (committed; the durable board layout)
```json
{
  "status": { "12": "in_progress", "8": "backlog" },   // OPEN issues only
  "order":  [12, 8, 15, 3]                              // global rank; columns derived
}
```

### Board read-file — `roadmap.json` (generated; gitignored)
The companion regenerates this on every sync/write. Same shape the board renders
today, so **the board needs no read-side changes**:
```json
{
  "updated_at": "…",
  "items": [
    { "ref": 12, "id": "gh-12", "title": "…", "notes": "<issue body>", "status": "in_progress" }
  ]
}
```
`ref` = issue number, `status` = sidecar (or `done` if closed), items sorted by
sidecar `order`.

## Components

```
GitHub Issues  ──gh──►  Companion  ──writes──►  roadmap.json ──poll──►  Board
   ▲                    (serves board,          (generated)            (static page)
   └──── gh writes ──── merges, syncs) ◄──POST writes── Board controls
                              │
                        .vibemap/meta.json (sidecar)
```

The companion **replaces `python -m http.server`**: it serves the board's static
files, keeps `roadmap.json` fresh, and exposes write endpoints. Uses `gh` for all
GitHub access, so auth is handled (no tokens in the client).

Only REST-backed `gh` commands are needed — **no GraphQL / Projects v2**:
`gh issue list --json number,title,body,state`, `gh issue create`,
`gh issue edit`, `gh issue close` / `reopen`.

## Sync / merge (the read path)

Runs on companion start, on a timer (~30–60s, to catch GitHub-side edits), and
immediately after any local write.

1. `gh issue list --state all --json number,title,body,state` → current issues.
2. Load sidecar (`status`, `order`).
3. For each issue: `closed → done`; `open → status = sidecar.status[n] || "backlog"`.
4. **Reconcile** (see below) so the sidecar matches reality.
5. Sort items by sidecar `order`; write `roadmap.json`.

## Reconciliation (the one real hard part)

Deterministic rule: **GitHub wins for content + open/closed; the sidecar wins for
backlog↔in-progress split + order.** On each sync:

- **New issue on GitHub** (not in sidecar) → add to `status` as `backlog`, append
  to `order`. (Appears in Backlog automatically.)
- **Issue gone** (deleted / transferred) → drop from `status` and `order`.
- **Closed on GitHub** → renders as `done` regardless of sidecar; leave its
  `status` entry alone (used again if reopened).
- **Reopened on GitHub** → falls back to `sidecar.status[n]`, else `backlog`.
- **Title/body edited on GitHub** → flows straight in (GitHub canonical).
- **Order** contains only currently-known issue numbers; new ones appended,
  missing ones removed.

Net: any change made directly on GitHub is absorbed without conflict; the only
locally-owned facts (in/backlog split, rank) are preserved and defaulted sanely.

## Write paths

| Action | GitHub call | Sidecar | Cost |
|---|---|---|---|
| Create card (#25) | `gh issue create` → get `#n` | add `status=backlog`, append `order` | 1 API |
| Edit title/notes (#28) | `gh issue edit n --title --body` | — | 1 API |
| Move Backlog ↔ In Progress | — | update `status[n]` | **local only, no API, no noise** |
| Reorder (drag) | — | update `order` | **local only** |
| Move to Done | `gh issue close n` | — | 1 API |
| Move out of Done | `gh issue reopen n` | `status[n]` = target | 1 API |

The high-frequency churn (reordering, backlog/in-progress shuffling) is **local**,
so GitHub only sees meaningful changes — this is what keeps issue-tracker noise low.

## Migration from today's roadmap.json

One-time script: for each current item, `gh issue create --title <title> --body
<notes>` (create done items then `gh issue close`); build `.vibemap/meta.json`
from current `status`/order; gitignore the generated `roadmap.json`; drop `seq`.
Refs renumber to issue numbers (accepted as trivial).

## Phasing

1. **Read-only mirror** — companion syncs issues → `roadmap.json`
   (done=closed, all open → backlog); board displays. Proves the pipeline.
2. **Local writes** — swimlane move + reorder via sidecar (no API).
3. **GitHub writes** — create / edit-text / close-reopen via companion.
4. **Reconciliation hardening** — timer sync + the rules above.

## Open questions

- Companion stack: Node vs Python (either; Node if the board ever wants a richer API).
- Sync cadence vs rate limits: 30–60s polling is trivially within 5000/hr.
- Optional: mirror status to a GitHub label so Issues-browsers see it (adds noise; default off).
- Ordering scope: single global rank (recommended) vs per-column arrays.
