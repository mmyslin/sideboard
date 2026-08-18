#!/usr/bin/env python3
"""Sideboard router — one always-on server that follows the ACTIVE project.

Why a router (see docs/github-sync-design.md, #35): in this Claude Code setup
every session runs from $HOME, so a hook's payload can't tell projects apart by
cwd — the only signal is the session TITLE. A global hook POSTs the active
session_title to /active; the router resolves title -> project dir (token match
against ~/Documents/Projects, cached in a registry) and serves that project's
board. The preview pane is pinned to :7777 once; its content then follows
whichever project you're working in — no per-project companions, no port fights.

GitHub mode only: a project is a git repo whose roadmap lives in GitHub Issues,
with a committed `.sideboard/meta.json` sidecar holding the swimlane split, card
order, and per-tag colors. Discovery keys off that sidecar; the router rebuilds
the board by reconciling the sidecar against `gh issue list`.

  python3 sideboard_router.py     # serve :7777, follow the active project
"""
import json, os, re, sys, shutil, subprocess, threading, time, datetime, uuid, http.server, urllib.parse

HOME = os.path.expanduser("~")
ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
# Board HTML location, most-specific first: explicit env override, next to the
# router (legacy flat install: install.sh copies both into ~/.claude/skills/...),
# then one level up (plugin layout: router lives in scripts/, board at plugin root).
BOARD_HTML = next(
    (p for p in (
        os.environ.get("SIDEBOARD_BOARD_HTML"),
        os.path.join(ROUTER_DIR, "roadmap-board.html"),
        os.path.join(os.path.dirname(ROUTER_DIR), "roadmap-board.html"),
    ) if p and os.path.exists(p)),
    os.path.join(ROUTER_DIR, "roadmap-board.html"),
)
REGISTRY = os.path.join(HOME, ".claude", "sideboard-projects.json")
PROJECTS_ROOT = os.path.abspath(os.environ.get(
    "SIDEBOARD_PROJECTS_ROOT", os.path.join(HOME, "Documents", "Projects")))
PORT = int(os.environ.get("SIDEBOARD_PORT", "7777"))
# Loopback-only guard (#57). Cross-site browser requests always carry an Origin and
# a Host of the page they came from; a DNS-rebound page reaches us with a foreign
# Host. Local callers (the hook, curl) send the real loopback Host and no Origin.
_ALLOWED_HOSTS = frozenset({f"127.0.0.1:{PORT}", f"localhost:{PORT}"})
_ALLOWED_ORIGINS = frozenset({f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"})
SYNC_SECONDS = int(os.environ.get("SIDEBOARD_SYNC_SECONDS", "45"))
MAX_BODY = 1 << 20     # cap POST bodies at 1 MiB — a huge Content-Length shouldn't force a big alloc (#74)
ISSUE_LIMIT = int(os.environ.get("SIDEBOARD_ISSUE_LIMIT", "1000"))   # gh issue list page size (#76)
GH_TIMEOUT = int(os.environ.get("SIDEBOARD_GH_TIMEOUT", "60"))       # per-gh-call bound, seconds (#85)
ERROR_RETRY_SECONDS = int(os.environ.get("SIDEBOARD_ERROR_RETRY_SECONDS", "5"))   # retry faster while errored (#52)
SCHEMA = 2   # .sideboard/meta.json schema version (migrated forward on load); v2 added sequences (#47)

LOCK = threading.RLock()
STATE = {"active": None}     # active Project or None
CACHE = {}                   # dir -> Project (keeps fetched issues warm across switches)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- sequences (#47): ordered sets of >=2 issues, one LLM-titled chain per issue ----
def _new_seq_id():
    return "seq-" + uuid.uuid4().hex[:8]

def _norm_sequences(raw):
    """Coerce sidecar sequences to [{id, title, items:[str,...]}] with de-duped items."""
    out = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        items = list(dict.fromkeys(str(x) for x in (s.get("items") or [])))
        out.append({"id": str(s.get("id") or _new_seq_id()),
                    "title": str(s.get("title") or ""), "items": items})
    return out


def _group_sequences(order, sequences):
    """Force each sequence's members to sit consecutively (in sequence order) so a
    chain is never interrupted by unrelated issues. The block lands at the position
    of the sequence's earliest current member; everything else keeps its order."""
    pos = {n: i for i, n in enumerate(order)}
    anchor_block, members = {}, set()
    for s in sequences:
        present = [n for n in s["items"] if n in pos]
        if len(present) < 2:
            continue
        members.update(present)
        anchor_block[min(pos[n] for n in present)] = present   # earliest member's index -> ordered block
    if not anchor_block:
        return order
    out = []
    for i, n in enumerate(order):
        if i in anchor_block:
            out.extend(anchor_block[i])        # emit the whole chain here, in sequence order
        elif n not in members:
            out.append(n)                      # other members are skipped (already emitted in their block)
    return out


# ---- session title -> project directory ------------------------------------
def _tokens(s):
    return set(t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t)


def _load_registry():
    try:
        return json.load(open(REGISTRY))
    except Exception:
        return {}


def _save_registry(reg):
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    tmp = f"{REGISTRY}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2)
    os.replace(tmp, REGISTRY)      # atomic; never leaves a torn registry (#77)


def _migrate_registry():
    """One-time: carry the legacy vibemap-projects.json to the new filename."""
    old = os.path.join(HOME, ".claude", "vibemap-projects.json")
    if os.path.exists(old) and not os.path.exists(REGISTRY):
        try:
            os.rename(old, REGISTRY)
            print(f"[sideboard] migrated registry {old} -> {REGISTRY}", flush=True)
        except OSError:
            pass


def _candidate_dirs():
    out = []
    try:
        for name in sorted(os.listdir(PROJECTS_ROOT)):
            d = os.path.join(PROJECTS_ROOT, name)
            if os.path.isdir(d) and (os.path.exists(os.path.join(d, ".sideboard", "meta.json"))
                                     or os.path.exists(os.path.join(d, ".vibemap", "meta.json"))):  # legacy, migrated on open
                out.append(d)
    except FileNotFoundError:
        pass
    return out


def resolve_dir(title):
    """Map a session title to a project dir. Registry wins (user-editable override);
    else the dir whose name tokens best overlap the title, requiring a STRICT
    MAJORITY of the dir's tokens (>0.5) and breaking ties toward the more-specific
    dir (more matched tokens). Only full-coverage (1.0) matches are cached; fuzzier
    ones re-resolve each session so an ambiguous guess never becomes permanent (#62).

    The strict-majority rule fixes two mis-bindings: a single-token dir (`sideboard`)
    only matches on a full hit, not as a subset of `sideboard-docs`; and a generic
    token (`tracker`) no longer half-matches any title mentioning it."""
    if not title:
        return None
    # Guard the registry read-modify-write: concurrent /active handler threads must
    # not each load the same snapshot and clobber the other's new mapping (#77).
    with LOCK:
        reg = _load_registry()
        mapped = reg.get(title)
        if mapped and os.path.isdir(mapped):
            return mapped
        tt = _tokens(title)
        if not tt:
            return None
        best = None                            # ((score, overlap), dir)
        for d in _candidate_dirs():
            dt = _tokens(os.path.basename(d))
            if not dt:
                continue
            overlap = len(tt & dt)
            score = overlap / len(dt)          # fraction of the dir's name tokens found in the title
            if score <= 0.5:                   # require a strict majority, not just half
                continue
            cand = ((score, overlap), d)
            if best is None or cand[0] > best[0]:   # higher score, then more matched tokens (specificity)
                best = cand
        if best is None:
            return None
        if best[0][0] >= 1.0:                  # persist only confident, full-coverage matches
            reg[title] = best[1]
            _save_registry(reg)
        return best[1]


def project_name(d):
    """Display name for a project dir: its registered session title, else the dir name."""
    for title, path in _load_registry().items():
        if path == d:
            return title
    return os.path.basename(d)


def _has_sidecar(d):
    return (os.path.exists(os.path.join(d, ".sideboard", "meta.json"))
            or os.path.exists(os.path.join(d, ".vibemap", "meta.json")))


def project_id(d):
    """The board-facing id for a project dir: its basename when it sits directly
    under PROJECTS_ROOT, else its FULL path. Basenames are ambiguous for
    registry-mapped projects outside the root — a bare name would resolve to a
    same-named dir under the root (or nothing), routing writes to the wrong
    repo (#81)."""
    if os.path.dirname(os.path.realpath(d)) == os.path.realpath(PROJECTS_ROOT):
        return os.path.basename(d)
    return d


def project_by_id(pid):
    """Resolve a board-sent project id to a directory. Ids are attacker-adjacent
    (query param / POST body), so resolution is an ALLOW-LIST, not a path join:
    a bare name must be a sidecar-bearing dir directly under PROJECTS_ROOT (or a
    registry value there); an absolute path must realpath-match a registry value
    or a sidecar-bearing dir under the root. No `../` traversal (#59), no
    resolving arbitrary dirs (#90), no basename collisions for out-of-root
    registry projects (#81)."""
    if not pid:
        return None
    root = os.path.realpath(PROJECTS_ROOT)
    reg_paths = {os.path.realpath(p) for p in _load_registry().values()}
    if os.path.isabs(pid):
        d = os.path.realpath(pid)
        if not os.path.isdir(d):
            return None
        try:
            in_root = os.path.commonpath([root, d]) == root and os.path.dirname(d) == root
        except ValueError:
            in_root = False
        if d in reg_paths or (in_root and _has_sidecar(d)):
            return d
        return None
    if pid in (".", "..") or os.sep in pid or (os.altsep and os.altsep in pid):
        return None
    d = os.path.realpath(os.path.join(root, pid))
    try:
        if os.path.commonpath([root, d]) != root:
            return None
    except ValueError:      # different drive, etc.
        return None
    if not os.path.isdir(d) or not (_has_sidecar(d) or d in reg_paths):
        return None
    return d


def list_projects():
    """All Sideboard projects — sidecar dirs under PROJECTS_ROOT plus registry-
    mapped dirs outside it (#81) — for the board's switcher dropdown."""
    active = STATE["active"]
    dirs = list(_candidate_dirs())
    seen = {os.path.realpath(d) for d in dirs}
    for p in _load_registry().values():
        if os.path.isdir(p) and os.path.realpath(p) not in seen:
            seen.add(os.path.realpath(p))
            dirs.append(p)
    return [{"id": project_id(d), "name": project_name(d),
             "active": bool(active) and active.path == d}
            for d in dirs]


# ---- macOS TCC / permission resilience (#46) -------------------------------
# gh/git need a readable working directory. ~/Documents is TCC-protected, so a
# router cold-booted by a hook into a permission-poor context gets EPERM
# ("operation not permitted" / "unable to read current working directory") for
# every call made from the project dir. Run gh with an explicit `-R owner/repo`
# from a cwd that is never sandboxed, so the API calls don't touch the project
# folder at all; only one-time repo detection has to read it.
SAFE_CWD = os.path.dirname(os.path.abspath(__file__))
_PERM_MARKERS = ("operation not permitted", "unable to read current working directory")
def _is_perm_error(text):
    t = (text or "").lower()
    return any(m in t for m in _PERM_MARKERS)
_PERM_MSG = ("macOS blocked this router from reading the project folder in "
             "~/Documents. Restart it: run ./sideboard-up.sh in the repo.")

# A transient connectivity error (laptop sleep/wake, wifi switch) — treat gently: keep
# the last-known board, say "reconnecting", and retry fast until it clears (#52).
_NET_MARKERS = ("error connecting to", "could not resolve host", "network is unreachable",
                "connection refused", "no such host", "dial tcp", "timeout", "timed out",
                "temporary failure in name resolution", "check your internet connection")
def _is_net_error(text):
    t = (text or "").lower()
    return any(m in t for m in _NET_MARKERS)
_NET_MSG = "Can't reach GitHub — reconnecting…"

def access_ok():
    """Can this process read the projects root? macOS TCC can deny a hook-launched
    daemon access to ~/Documents; when it does, the launcher should relaunch the
    router from a granted context instead of serving broken boards. Exposed on
    /healthz and the /active response so the hook/up-script can self-heal (#46)."""
    try:
        os.listdir(PROJECTS_ROOT)
    except PermissionError:
        return False          # TCC denied ~/Documents to this process
    except OSError:
        pass                  # missing/other root — not a permission wall; don't trigger a relaunch
    return True


# ---- a single project ------------------------------------------------------
class Project:
    def __init__(self, path):
        self.path = path
        self.title = None
        self._migrate_sidecar(path)     # legacy .vibemap/ -> .sideboard/ (one-time, per project)
        self.meta_path = os.path.join(path, ".sideboard", "meta.json")
        self.error = None          # human-readable reason the board can't load (no repo / gh auth / issues)
        self._detect_err = None    # set by _detect_repo when access was denied (EPERM); surfaced by sync (#46)
        self.repo = self._detect_repo()
        self.issues = []
        self.issues_complete = True   # False when the last fetch hit the page limit (#76/#84)
        self.synced_at = None      # stamped on each sync; keeps updated_at stable between syncs (#42)
        self.lock = threading.RLock()

    @staticmethod
    def _migrate_sidecar(path):
        old, new = os.path.join(path, ".vibemap"), os.path.join(path, ".sideboard")
        if os.path.isdir(old) and not os.path.exists(new):
            os.rename(old, new)
            print(f"[sideboard] migrated sidecar {old} -> {new}", flush=True)

    def _detect_repo(self):
        # The one call that must read the project dir — to learn owner/repo.
        try:
            r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                               cwd=self.path, text=True, capture_output=True, timeout=10)
            slug = (r.stdout or "").strip()
            if slug:
                self._detect_err = None
                return slug
            if _is_perm_error(r.stderr):
                self._detect_err = _PERM_MSG
            elif _is_net_error(r.stderr):
                self._detect_err = _NET_MSG
            return None
        except Exception as e:
            if _is_perm_error(str(e)):
                self._detect_err = _PERM_MSG
            elif _is_net_error(str(e)):
                self._detect_err = _NET_MSG
            return None

    def _gh(self, *args):
        # Run from a never-sandboxed cwd and target the repo explicitly, so the
        # call never depends on ~/Documents being accessible to this process (#46).
        # A repo-less project must NEVER call gh without -R: gh would resolve the
        # target from whatever checkout owns the cwd and silently file the user's
        # content in an unrelated (possibly public) repo (#83).
        if not self.repo:
            raise RuntimeError("no GitHub repo detected for this project")
        # Bounded: one wedged call (proxy black-hole, credential prompt) must not
        # halt the shared serial sync loop forever (#85).
        return subprocess.run(["gh", *args, "-R", self.repo], cwd=SAFE_CWD,
                              check=True, text=True, capture_output=True,
                              timeout=GH_TIMEOUT).stdout

    # -- sidecar (github mode) ------------------------------------------------
    def _quarantine_meta(self, reason):
        # A corrupt sidecar must not crash the loader (it would blank the board with
        # no reason AND make /active 500 every prompt -> relaunch storm, #60). Move it
        # aside and rebuild from GitHub on the next sync.
        bad = self.meta_path + ".corrupt.bak"
        try:
            os.replace(self.meta_path, bad)
        except OSError:
            pass
        print(f"[router] {reason}; quarantined sidecar -> {bad}", file=sys.stderr, flush=True)
        self.error = "Sidecar was corrupt — quarantined and rebuilding from GitHub."

    def _load_meta(self):
        try:
            m = json.load(open(self.meta_path))
        except FileNotFoundError:
            m = {}
        except PermissionError:
            self.error = _PERM_MSG      # sidecar in ~/Documents blocked by macOS TCC (#46)
            m = {}
        except (json.JSONDecodeError, ValueError):
            self._quarantine_meta("corrupt meta.json on load")
            m = {}
        return {"status": dict(m.get("status", {})), "order": [str(n) for n in m.get("order", [])],
                "tag_colors": dict(m.get("tag_colors", {})), "next_color": m.get("next_color", 0),
                "sequences": _norm_sequences(m.get("sequences", []))}

    def _save_meta(self, meta):
        stable = {"schema": SCHEMA,
                  "status": {k: meta["status"][k] for k in sorted(meta["status"], key=int)},
                  "order": meta["order"],
                  "next_color": meta.get("next_color", 0),
                  "tag_colors": {k: meta["tag_colors"][k] for k in sorted(meta.get("tag_colors", {}))},
                  "sequences": [{"id": s["id"], "title": s["title"], "items": [int(x) for x in s["items"]]}
                                for s in meta.get("sequences", [])]}
        tmp = f"{self.meta_path}.tmp.{os.getpid()}"
        try:
            os.makedirs(os.path.dirname(self.meta_path), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(stable, f, indent=2)
            os.replace(tmp, self.meta_path)   # atomic: never leaves a truncated sidecar (#60)
        except PermissionError:
            self.error = _PERM_MSG      # sidecar in ~/Documents blocked by macOS TCC (#46)
            try: os.remove(tmp)
            except OSError: pass

    def migrate(self):
        """Upgrade an older sidecar to the current schema."""
        try:
            raw = json.load(open(self.meta_path))
        except FileNotFoundError:
            return
        except PermissionError:
            self.error = _PERM_MSG      # sidecar in ~/Documents blocked by macOS TCC (#46)
            return
        except (json.JSONDecodeError, ValueError):
            self._quarantine_meta("corrupt meta.json on migrate")   # else /active 500s every prompt (#60)
            return
        v = int(raw.get("schema", 0))
        if v >= SCHEMA:
            return
        shutil.copy(self.meta_path, f"{self.meta_path}.v{v}.bak")
        if v < 1:                       # v0 -> v1: per-tag colors were added
            raw.setdefault("tag_colors", {})
            raw.setdefault("next_color", 0)
        if v < 2:                       # v1 -> v2: sequences were added (#47)
            raw.setdefault("sequences", [])
        self._save_meta({"status": raw.get("status", {}),
                         "order": [str(n) for n in raw.get("order", [])],
                         "tag_colors": raw.get("tag_colors", {}),
                         "next_color": raw.get("next_color", 0),
                         "sequences": _norm_sequences(raw.get("sequences", []))})
        print(f"[router] migrated {self.path} sidecar v{v} -> v{SCHEMA}", flush=True)

    def _reconcile(self, issues, meta, complete=True):
        # `complete` is False when the issue list was truncated at the API page
        # limit — then we must NOT treat missing issues as deleted (that would purge
        # real cards' status/order/sequence records); we only add, never prune (#76).
        status, order = dict(meta["status"]), list(meta["order"])
        present = {str(i["number"]) for i in issues}
        for i in issues:
            n = str(i["number"])
            if i["state"].lower() == "open" and n not in status:
                status[n] = "backlog"
        if complete:
            status = {n: s for n, s in status.items() if n in present}
            order = list(dict.fromkeys(n for n in order if n in present))
        else:
            order = list(dict.fromkeys(order))
        for i in issues:
            n = str(i["number"])
            if n not in order:
                order.append(n)
        tag_colors, next_color = dict(meta["tag_colors"]), meta["next_color"]
        for name in sorted({l["name"] for i in issues for l in i.get("labels", [])}):
            if name not in tag_colors:
                tag_colors[name] = next_color
                next_color += 1
        # Sequences (#47): drop deleted issues, enforce one-sequence-per-issue,
        # and auto-dissolve any chain that falls below 2 items. Done issues stay
        # in the chain (they're the completed steps the ordering is about).
        sequences, seen = [], set()
        for s in meta.get("sequences", []):
            items = []
            for n in s["items"]:
                if (n in present or not complete) and n not in seen:
                    items.append(n); seen.add(n)
            if len(items) >= 2:
                sequences.append({"id": s.get("id") or _new_seq_id(),
                                  "title": s.get("title", ""), "items": items})
        order = _group_sequences(order, sequences)   # keep each chain's cards consecutive
        return {"status": status, "order": order, "tag_colors": tag_colors,
                "next_color": next_color, "sequences": sequences}

    def sync(self):
        """Re-fetch issues + reconcile the sidecar. Records a human-readable
        reason in self.error (surfaced on the board) if GitHub can't be reached
        — no repo, gh not authenticated, or Issues disabled — instead of
        silently serving an empty board."""
        with self.lock:
            if not self.repo:
                self.repo = self._detect_repo()   # self-heal: retry detection each poll (#46)
            if not self.repo:
                self.error = self._detect_err or (
                    "No GitHub repo detected here. Sideboard is GitHub-only: "
                    "run it from a repo, and make sure `gh auth login` is done.")
                return
            try:
                issues = json.loads(self._gh("issue", "list", "--state", "all", "--limit", str(ISSUE_LIMIT),
                                             "--json", "number,title,body,state,labels"))
            except subprocess.TimeoutExpired:
                self.error = _NET_MSG             # treat a wedged gh like a network blip (#85)
                return
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or "").strip()
                self.error = (_PERM_MSG if _is_perm_error(stderr) else
                              _NET_MSG if _is_net_error(stderr) else
                              f"Couldn't read GitHub Issues for {self.repo}: "
                              f"{stderr or 'is `gh` authenticated and are Issues enabled?'}")
                return
            self.issues = issues
            self.error = None                     # clear stale errors; the sidecar ops below may re-set it
            # A full page means more issues exist beyond it. Store the flag on the
            # Project — every later reconcile (sequence writes included) must honor
            # it, or a seq edit re-runs the purge #76 removed (#84).
            self.issues_complete = len(issues) < ISSUE_LIMIT
            if not self.issues_complete:
                print(f"[router] {self.repo}: issue list hit the {ISSUE_LIMIT} limit — not pruning "
                      f"missing issues (raise SIDEBOARD_ISSUE_LIMIT).", file=sys.stderr, flush=True)
            self._save_meta(self._reconcile(self.issues, self._load_meta(), self.issues_complete))
            if self.error:                        # _load_meta/_save_meta hit a permission wall (#46)
                return
            self.synced_at = _now()

    def board(self):
        with self.lock:
            bv = str(int(os.path.getmtime(BOARD_HTML)))
            # A transient network error keeps the last-known cards (just flags "reconnecting");
            # any other error blanks the board with the reason (#52).
            if self.error and self.error != _NET_MSG:
                return {"updated_at": self.synced_at or _now(), "project": self.title,
                        "project_id": project_id(self.path),
                        "mode": "github", "board_version": bv, "items": [], "error": self.error}
            meta = self._load_meta()
            by_num = {str(i["number"]): i for i in self.issues}
            seq_by_item = {}                       # issue -> its sequence + position (#47)
            for s in meta["sequences"]:
                for pos, n in enumerate(s["items"]):
                    seq_by_item[n] = {"id": s["id"], "title": s["title"], "pos": pos, "len": len(s["items"])}
            items = []
            for n in meta["order"]:
                i = by_num.get(n)
                if not i:
                    continue
                closed = i["state"].lower() == "closed"
                items.append({"ref": int(n), "id": f"gh-{n}", "title": i["title"],
                              "notes": i.get("body") or "",
                              "status": "done" if closed else meta["status"].get(n, "backlog"),
                              "labels": [{"name": l["name"], "colorIndex": meta["tag_colors"].get(l["name"])}
                                         for l in i.get("labels", [])],
                              "sequence": seq_by_item.get(n)})
            # updated_at is the last SYNC time, not now — so the polled payload is byte-identical
            # between syncs and the board doesn't re-render (and reset scroll) every poll (#42)
            out = {"updated_at": self.synced_at or _now(), "project": self.title, "mode": "github",
                   "project_id": project_id(self.path),
                   "board_version": bv, "items": items,
                   "sequences": [{"id": s["id"], "title": s["title"], "items": [int(x) for x in s["items"]]}
                                 for s in meta["sequences"]]}
            if self.error == _NET_MSG:            # reconnecting: last-known cards + a soft indicator (#52)
                out["error"] = self.error
                out["error_offline"] = True
            return out

    # -- writes ---------------------------------------------------------------
    def apply_drop(self, number, status, order):
        n = str(number)
        with self.lock:
            issue = next((i for i in self.issues if str(i["number"]) == n), None)
            closed = bool(issue) and issue["state"].lower() == "closed"
            meta = self._load_meta()
            if status == "done":
                if issue and not closed:
                    self._gh("issue", "close", n)
                    issue["state"] = "closed"   # keep in-memory state consistent until the next sync (#75)
                meta["status"].pop(n, None)
            elif status in ("backlog", "in_progress"):
                if closed:
                    self._gh("issue", "reopen", n)
                    issue["state"] = "open"     # (#75)
                meta["status"][n] = status
            if order:
                # Only accept numbers this project knows — a stale pane's order from
                # ANOTHER project must not wholesale-replace this one's curation (#80).
                known = self._present() | set(meta["order"])
                new_order = [str(x) for x in order if str(x) in known]
                if not self.issues_complete:
                    # Truncated fetch: the client only rendered (and re-ordered) the
                    # fetched page — keep beyond-page issues' positions appended (#84).
                    new_order += [n for n in meta["order"] if n not in new_order]
                meta["order"] = new_order
            self._save_meta(meta)
        self.sync()

    def create(self, title, body):
        url = self._gh("issue", "create", "--title", title, "--body", body or "").strip().splitlines()[-1]
        self.sync()
        return int(url.rsplit("/", 1)[-1])

    def edit(self, n, title, body):
        self._gh("issue", "edit", str(n), "--title", title, "--body", body or "")
        self.sync()

    def label(self, number, add=None, remove=None):
        if add:
            subprocess.run(["gh", "label", "create", "-R", self.repo, "--", add], cwd=SAFE_CWD,
                           capture_output=True, text=True, timeout=GH_TIMEOUT)
            self._gh("issue", "edit", str(number), "--add-label", add)
        if remove:
            self._gh("issue", "edit", str(number), "--remove-label", remove)
        self.sync()

    # -- sequence writes (#47): sidecar-only, no gh round-trip; board reads
    #    _load_meta fresh each poll, so changes show up without a GitHub refetch.
    def _present(self):
        return {str(i["number"]) for i in self.issues}

    def _write_sequences(self, mutate):
        """Load meta, let mutate(sequences) change it in place, then reconcile+save.
        Never reconcile against an empty issue list: on a failed/pending first sync
        self.issues is [], and reconciling would treat every issue as deleted —
        wiping status, order, and every sequence from the sidecar (#61). Save the
        mutated meta as-is instead; the next real sync validates it."""
        with self.lock:
            meta = self._load_meta()
            res = mutate(meta["sequences"])
            # Honor the truncation flag here too — reconciling a truncated page with
            # complete=True would purge every beyond-page record on a seq edit (#84).
            self._save_meta(self._reconcile(self.issues, meta, self.issues_complete)
                            if self.issues else meta)
        return res

    def seq_create(self, items, title=""):
        present = self._present()
        items = [n for n in dict.fromkeys(str(x) for x in items) if n in present]
        if len(items) < 2:                      # a sequence needs >=2 real issues
            return None
        sid = _new_seq_id()
        def mut(seqs):
            for s in seqs:                       # 0/1 invariant: pull these out of any other chain
                s["items"] = [n for n in s["items"] if n not in items]
            seqs.append({"id": sid, "title": str(title or ""), "items": items})
            return sid
        return self._write_sequences(mut)

    def seq_update(self, sid, title=None, items=None):
        present = self._present()
        def mut(seqs):
            s = next((x for x in seqs if x["id"] == sid), None)
            if not s:
                return False
            if title is not None:
                s["title"] = str(title)
            if items is not None:                # reorder / set membership
                newitems = [n for n in dict.fromkeys(str(x) for x in items) if n in present]
                for other in seqs:
                    if other is not s:
                        other["items"] = [n for n in other["items"] if n not in newitems]
                s["items"] = newitems            # if it drops below 2, reconcile dissolves it
            return True
        return self._write_sequences(mut)

    def seq_dissolve(self, sid):
        def mut(seqs):
            n = len(seqs)
            seqs[:] = [x for x in seqs if x["id"] != sid]
            return len(seqs) != n
        return self._write_sequences(mut)

    def seq_move(self, number, sid):
        """Move issue `number` into sequence `sid` (appended); a falsy sid just
        removes it from whatever chain it's in. Enforces one-sequence-per-issue."""
        n, present = str(number), self._present()
        def mut(seqs):
            for s in seqs:
                s["items"] = [x for x in s["items"] if x != n]
            if sid and n in present:
                s = next((x for x in seqs if x["id"] == sid), None)
                if s:
                    s["items"].append(n)
            return True
        return self._write_sequences(mut)


def get_project(path):
    with LOCK:
        p = CACHE.get(path)
        if p is None:
            p = Project(path)
            p.migrate()
            CACHE[path] = p
        return p


def _safe_sync(p):
    try:
        p.sync()
    except Exception as e:
        print(f"[router] sync error ({p.path}): {e}", file=sys.stderr, flush=True)


def set_active(title):
    """Switch the served board to the project for `title`. Returns the Project or None."""
    path = resolve_dir(title)
    if not path:
        return None
    p = get_project(path)
    p.title = title
    with LOCK:
        changed = p is not STATE["active"]
        STATE["active"] = p
    if changed or not p.issues:
        threading.Thread(target=_safe_sync, args=(p,), daemon=True).start()
    return p


# ---- HTTP ------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 30   # bound each request read — a stalled/dribbling body must not pin a thread forever (#99)

    def log_message(self, *a):
        pass

    def _host_ok(self):
        # Reject foreign Host headers (DNS-rebinding defense, #57).
        return (self.headers.get("Host") or "").strip().lower() in _ALLOWED_HOSTS

    def _origin_ok(self):
        # Cross-site browser requests always send Origin; local curl/hook callers
        # send none. Allow absent; otherwise require a loopback origin (CSRF defense).
        origin = self.headers.get("Origin")
        if origin is not None:
            return origin.strip().lower() in _ALLOWED_ORIGINS
        ref = self.headers.get("Referer")
        if ref:
            try:
                u = urllib.parse.urlparse(ref)
                return f"{u.scheme}://{u.netloc}".lower() in _ALLOWED_ORIGINS
            except Exception:
                return False
        return True

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, '{"ok": false, "error": "forbidden host"}')
        path = self.path.split("?")[0]
        if path == "/healthz":
            p = STATE["active"]
            return self._send(200, json.dumps({"router": True, "active": p.title if p else None,
                                                "access_ok": access_ok()}))
        if path == "/projects":
            return self._send(200, json.dumps({"projects": list_projects()}))
        if path == "/roadmap.json":
            pid = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("project") or [None])[0]
            empty = {"updated_at": _now(), "project": None, "items": [],
                     "board_version": str(int(os.path.getmtime(BOARD_HTML)))}
            try:
                if pid:                                    # pinned view of a specific project
                    d = project_by_id(pid)
                    if not d:
                        return self._send(200, json.dumps(empty))
                    p = get_project(d)
                    p.title = project_name(d)
                    if not p.issues:
                        _safe_sync(p)                      # blocking first load so it shows right away
                    board = p.board()
                else:                                      # auto: follow the active project
                    p = STATE["active"]
                    board = p.board() if p else empty
            except Exception as e:
                print(f"[router] board error (project={pid}): {e}", file=sys.stderr, flush=True)
                board = empty
            return self._send(200, json.dumps(board, ensure_ascii=False))
        # Don't serve the board HTML for stray /api/ GETs — return JSON 404 so a
        # typo'd or GET-instead-of-POST API call reads as an error, not success (#67).
        if path.startswith("/api/"):
            return self._send(404, '{"ok": false, "error": "not found"}')
        # Fallback: serve the board for "/", "/roadmap-board.html", and ANY other GET path — so a
        # stale/odd pane URL restored on session return still renders the roadmap, not a 404.
        # (The client fetches /roadmap.json absolute, so it loads data even from a nested path.)
        v = str(int(os.path.getmtime(BOARD_HTML)))
        html = open(BOARD_HTML, encoding="utf-8").read().replace(
            "</head>", f'<script>window.__BV="{v}";</script>\n</head>', 1)
        self._send(200, html, "text/html; charset=utf-8")

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._send(403, '{"ok": false, "error": "forbidden origin"}')
        path = self.path.split("?")[0]
        try:
            clen = int(self.headers.get("Content-Length", 0) or 0)
            if clen > MAX_BODY:
                return self._send(413, '{"ok": false, "error": "body too large"}')
            body = json.loads(self.rfile.read(clen) or "{}")
            if path == "/active":
                p = set_active(body.get("session_title"))
                return self._send(200, json.dumps({"ok": True, "project": p.title if p else None,
                                                    "dir": p.path if p else None, "access_ok": access_ok()}))
            # Route the write to the project the pane is SHOWING (its rendered/pinned
            # id), not just whichever is active — a pinned/lagging pane must not mutate
            # the wrong repo (#58). Fall back to the active project only when no id is sent.
            pid = body.get("project")
            if pid:
                d = project_by_id(pid)
                if not d:
                    return self._send(404, json.dumps({"ok": False, "error": "unknown project"}))
                p = get_project(d)
            else:
                p = STATE["active"]
            if p is None:
                return self._send(409, json.dumps({"ok": False, "error": "no active project"}))
            # Defense in depth (#80): a write must target an issue that is actually on
            # the resolved project's board. Issue numbers collide across repos, so a
            # stale pane racing a project switch would otherwise mutate a real,
            # unrelated issue in the other repo.
            if path in ("/api/drop", "/api/edit", "/api/label", "/api/seq/move") \
               and str(int(body["number"])) not in {str(i["number"]) for i in p.issues}:
                return self._send(409, json.dumps({"ok": False, "error": "issue not on this project's board"}))
            if path == "/api/drop":
                p.apply_drop(int(body["number"]), body["status"], body.get("order"))
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/create":
                return self._send(200, json.dumps({"ok": True, "number": p.create(body["title"], body.get("notes", ""))}))
            if path == "/api/edit":
                p.edit(int(body["number"]), body["title"], body.get("notes", ""))
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/label":
                p.label(int(body["number"]), body.get("add"), body.get("remove"))
                return self._send(200, json.dumps({"ok": True}))
            # -- sequences (#47) --
            if path == "/api/seq/create":
                sid = p.seq_create(body.get("items", []), body.get("title", ""))
                return self._send(200 if sid else 400,
                                  json.dumps({"ok": bool(sid), "id": sid} if sid
                                             else {"ok": False, "error": "need >=2 existing issues"}))
            if path == "/api/seq/update":
                ok = p.seq_update(body["id"], body.get("title"), body.get("items"))
                return self._send(200 if ok else 404, json.dumps({"ok": ok}))
            if path == "/api/seq/dissolve":
                ok = p.seq_dissolve(body["id"])
                return self._send(200 if ok else 404, json.dumps({"ok": ok}))
            if path == "/api/seq/move":
                p.seq_move(int(body["number"]), body.get("id"))
                return self._send(200, json.dumps({"ok": True}))
            self._send(404, "{}")
        except Exception as e:
            print(f"[router] POST {path} error: {e}", file=sys.stderr, flush=True)
            # Detail stays in the log — str(e) can embed the full gh argv (repo
            # slug, issue title/body) or a filesystem path (#98).
            self._send(500, '{"ok": false, "error": "internal error (see router log)"}')


def sync_loop():
    backoff = ERROR_RETRY_SECONDS
    last_full = time.monotonic()
    while True:
        active = STATE["active"]
        # Fast-retry ONLY a transient network error, and only the errored project,
        # with exponential backoff (#68). Permanent errors (no repo / gh auth /
        # Issues disabled / TCC) must NOT hammer every cached project every 5s.
        if active and active.error == _NET_MSG:
            time.sleep(min(backoff, SYNC_SECONDS))
            backoff = min(backoff * 2, SYNC_SECONDS)
            _safe_sync(active)
            # _NET_MSG can be repo-SPECIFIC (a monorepo whose issue list times out
            # while the network is fine) — other pinned boards must not silently
            # starve behind it: keep the full sweep on its normal cadence (#86).
            if time.monotonic() - last_full >= SYNC_SECONDS:
                last_full = time.monotonic()
                for p in list(CACHE.values()):
                    if p is not active:
                        _safe_sync(p)
        else:
            backoff = ERROR_RETRY_SECONDS
            time.sleep(SYNC_SECONDS)
            last_full = time.monotonic()
            for p in list(CACHE.values()):     # keep the active project AND any pinned/viewed one fresh
                _safe_sync(p)


if __name__ == "__main__":
    _migrate_registry()
    threading.Thread(target=sync_loop, daemon=True).start()
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"[router] not starting — port {PORT} busy ({e}); another instance likely won.",
              file=sys.stderr, flush=True)
        sys.exit(0)
    print(f"[router] serving :{PORT}; following the active project (root: {PROJECTS_ROOT})", flush=True)
    print(f"[router] ~/Documents access: {'ok' if access_ok() else 'DENIED (macOS TCC) — boards will show the restart hint (#46)'}", flush=True)
    server.serve_forever()
