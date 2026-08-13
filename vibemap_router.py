#!/usr/bin/env python3
"""VibeMap router — one always-on server that follows the ACTIVE project.

Why a router (see docs/github-sync-design.md, #35): in this Claude Code setup
every session runs from $HOME, so a hook's payload can't tell projects apart by
cwd — the only signal is the session TITLE. A global hook POSTs the active
session_title to /active; the router resolves title -> project dir (token match
against ~/Documents/Projects, cached in a registry) and serves that project's
board. The preview pane is pinned to :7777 once; its content then follows
whichever project you're working in — no per-project companions, no port fights.

Supports both modes per project: github mode (.vibemap/meta.json + gh issues)
and legacy local-file mode (roadmap.json, served read-only).

  python3 vibemap_router.py     # serve :7777, follow the active project
"""
import json, os, re, sys, shutil, subprocess, threading, time, datetime, http.server

HOME = os.path.expanduser("~")
ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
BOARD_HTML = os.path.join(ROUTER_DIR, "roadmap-board.html")
REGISTRY = os.path.join(HOME, ".claude", "vibemap-projects.json")
PROJECTS_ROOT = os.path.abspath(os.environ.get(
    "VIBEMAP_PROJECTS_ROOT", os.path.join(HOME, "Documents", "Projects")))
PORT = int(os.environ.get("VIBEMAP_PORT", "7777"))
SYNC_SECONDS = int(os.environ.get("VIBEMAP_SYNC_SECONDS", "45"))
SCHEMA = 1   # mirrors github_companion.SCHEMA

LOCK = threading.RLock()
STATE = {"active": None}     # active Project or None
CACHE = {}                   # dir -> Project (keeps fetched issues warm across switches)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    json.dump(reg, open(REGISTRY, "w"), indent=2)


def _candidate_dirs():
    out = []
    try:
        for name in sorted(os.listdir(PROJECTS_ROOT)):
            d = os.path.join(PROJECTS_ROOT, name)
            if os.path.isdir(d) and (os.path.exists(os.path.join(d, ".vibemap", "meta.json"))
                                     or os.path.exists(os.path.join(d, "roadmap.json"))):
                out.append(d)
    except FileNotFoundError:
        pass
    return out


def resolve_dir(title):
    """Map a session title to a project dir. Registry wins; else best token
    overlap with a dir name (>=50% of the dir's tokens present in the title);
    the resolved pair is cached to the registry (user-editable for overrides)."""
    if not title:
        return None
    reg = _load_registry()
    mapped = reg.get(title)
    if mapped and os.path.isdir(mapped):
        return mapped
    tt = _tokens(title)
    if not tt:
        return None
    best, best_score = None, 0.0
    for d in _candidate_dirs():
        dt = _tokens(os.path.basename(d))
        if not dt:
            continue
        score = len(tt & dt) / len(dt)     # fraction of the dir's name tokens found in the title
        if score > best_score:
            best, best_score = d, score
    if best and best_score >= 0.5:
        reg[title] = best
        _save_registry(reg)
        return best
    return None


# ---- a single project ------------------------------------------------------
class Project:
    def __init__(self, path):
        self.path = path
        self.title = None
        self.meta_path = os.path.join(path, ".vibemap", "meta.json")
        self.roadmap_json = os.path.join(path, "roadmap.json")
        self.github = os.path.exists(self.meta_path)
        self.repo = self._detect_repo() if self.github else None
        self.issues = []
        self.synced_at = None      # stamped on each sync; keeps updated_at stable between syncs (#42)
        self.lock = threading.RLock()

    def _detect_repo(self):
        try:
            r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                               cwd=self.path, text=True, capture_output=True, timeout=10)
            return (r.stdout or "").strip() or None
        except Exception:
            return None

    def _gh(self, *args):
        return subprocess.run(["gh", *args], cwd=self.path, check=True, text=True, capture_output=True).stdout

    # -- sidecar (github mode) ------------------------------------------------
    def _load_meta(self):
        try:
            m = json.load(open(self.meta_path))
        except FileNotFoundError:
            m = {}
        return {"status": dict(m.get("status", {})), "order": [str(n) for n in m.get("order", [])],
                "tag_colors": dict(m.get("tag_colors", {})), "next_color": m.get("next_color", 0)}

    def _save_meta(self, meta):
        os.makedirs(os.path.dirname(self.meta_path), exist_ok=True)
        stable = {"schema": SCHEMA,
                  "status": {k: meta["status"][k] for k in sorted(meta["status"], key=int)},
                  "order": meta["order"],
                  "next_color": meta.get("next_color", 0),
                  "tag_colors": {k: meta["tag_colors"][k] for k in sorted(meta.get("tag_colors", {}))}}
        json.dump(stable, open(self.meta_path, "w"), indent=2)

    def migrate(self):
        """Upgrade an older sidecar to the current schema (mirrors github_companion)."""
        if not self.github:
            return
        try:
            raw = json.load(open(self.meta_path))
        except FileNotFoundError:
            return
        v = int(raw.get("schema", 0))
        if v >= SCHEMA:
            return
        shutil.copy(self.meta_path, f"{self.meta_path}.v{v}.bak")
        if v < 1:                       # v0 -> v1: per-tag colors were added
            raw.setdefault("tag_colors", {})
            raw.setdefault("next_color", 0)
        self._save_meta({"status": raw.get("status", {}),
                         "order": [str(n) for n in raw.get("order", [])],
                         "tag_colors": raw.get("tag_colors", {}),
                         "next_color": raw.get("next_color", 0)})
        print(f"[router] migrated {self.path} sidecar v{v} -> v{SCHEMA}", flush=True)

    def _reconcile(self, issues, meta):
        status, order = dict(meta["status"]), list(meta["order"])
        present = {str(i["number"]) for i in issues}
        for i in issues:
            n = str(i["number"])
            if i["state"].lower() == "open" and n not in status:
                status[n] = "backlog"
        status = {n: s for n, s in status.items() if n in present}
        order = list(dict.fromkeys(n for n in order if n in present))
        for i in issues:
            n = str(i["number"])
            if n not in order:
                order.append(n)
        tag_colors, next_color = dict(meta["tag_colors"]), meta["next_color"]
        for name in sorted({l["name"] for i in issues for l in i.get("labels", [])}):
            if name not in tag_colors:
                tag_colors[name] = next_color
                next_color += 1
        return {"status": status, "order": order, "tag_colors": tag_colors, "next_color": next_color}

    def sync(self):
        """Re-fetch issues + reconcile the sidecar (github mode); no-op for local mode."""
        with self.lock:
            if not self.github:
                return
            self.issues = json.loads(self._gh("issue", "list", "--state", "all", "--limit", "1000",
                                              "--json", "number,title,body,state,labels"))
            self._save_meta(self._reconcile(self.issues, self._load_meta()))
            self.synced_at = _now()

    def board(self):
        with self.lock:
            bv = str(int(os.path.getmtime(BOARD_HTML)))
            if not self.github:
                try:
                    data = json.load(open(self.roadmap_json))
                except Exception:
                    data = {"items": []}
                data["project"] = self.title or data.get("project")
                data["mode"] = "local"
                data["board_version"] = bv
                return data
            meta = self._load_meta()
            by_num = {str(i["number"]): i for i in self.issues}
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
                                         for l in i.get("labels", [])]})
            # updated_at is the last SYNC time, not now — so the polled payload is byte-identical
            # between syncs and the board doesn't re-render (and reset scroll) every poll (#42)
            return {"updated_at": self.synced_at or _now(), "project": self.title, "mode": "github",
                    "board_version": bv, "items": items}

    # -- writes (github mode; local mode is read-only) ------------------------
    def apply_drop(self, number, status, order):
        if not self.github:
            return
        n = str(number)
        with self.lock:
            issue = next((i for i in self.issues if str(i["number"]) == n), None)
            closed = bool(issue) and issue["state"].lower() == "closed"
            meta = self._load_meta()
            if status == "done":
                if issue and not closed:
                    self._gh("issue", "close", n)
                meta["status"].pop(n, None)
            elif status in ("backlog", "in_progress"):
                if closed:
                    self._gh("issue", "reopen", n)
                meta["status"][n] = status
            if order:
                meta["order"] = [str(x) for x in order]
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
            subprocess.run(["gh", "label", "create", add], cwd=self.path, capture_output=True, text=True)
            self._gh("issue", "edit", str(number), "--add-label", add)
        if remove:
            self._gh("issue", "edit", str(number), "--remove-label", remove)
        self.sync()


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
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            p = STATE["active"]
            return self._send(200, json.dumps({"router": True, "active": p.title if p else None}))
        if path in ("/", "/roadmap-board.html"):
            v = str(int(os.path.getmtime(BOARD_HTML)))
            html = open(BOARD_HTML, encoding="utf-8").read().replace(
                "</head>", f'<script>window.__BV="{v}";</script>\n</head>', 1)
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/roadmap.json":
            p = STATE["active"]
            if p is None:
                board = {"updated_at": _now(), "project": None, "items": [],
                         "board_version": str(int(os.path.getmtime(BOARD_HTML)))}
            else:
                try:
                    board = p.board()
                except Exception as e:
                    print(f"[router] board error ({p.path}): {e}", file=sys.stderr, flush=True)
                    board = {"updated_at": _now(), "project": p.title, "items": [],
                             "board_version": str(int(os.path.getmtime(BOARD_HTML)))}
            return self._send(200, json.dumps(board, ensure_ascii=False))
        self._send(404, "{}")

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            if path == "/active":
                p = set_active(body.get("session_title"))
                return self._send(200, json.dumps({"ok": True, "project": p.title if p else None,
                                                    "dir": p.path if p else None}))
            p = STATE["active"]
            if p is None:
                return self._send(409, json.dumps({"ok": False, "error": "no active project"}))
            if path == "/api/drop":
                p.apply_drop(body["number"], body["status"], body.get("order"))
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/create":
                return self._send(200, json.dumps({"ok": True, "number": p.create(body["title"], body.get("notes", ""))}))
            if path == "/api/edit":
                p.edit(body["number"], body["title"], body.get("notes", ""))
                return self._send(200, json.dumps({"ok": True}))
            if path == "/api/label":
                p.label(body["number"], body.get("add"), body.get("remove"))
                return self._send(200, json.dumps({"ok": True}))
            self._send(404, "{}")
        except Exception as e:
            print(f"[router] POST {path} error: {e}", file=sys.stderr, flush=True)
            self._send(500, json.dumps({"ok": False, "error": str(e)}))


def sync_loop():
    while True:
        time.sleep(SYNC_SECONDS)
        p = STATE["active"]
        if p:
            _safe_sync(p)


if __name__ == "__main__":
    threading.Thread(target=sync_loop, daemon=True).start()
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"[router] not starting — port {PORT} busy ({e}); another instance likely won.",
              file=sys.stderr, flush=True)
        sys.exit(0)
    print(f"[router] serving :{PORT}; following the active project (root: {PROJECTS_ROOT})", flush=True)
    server.serve_forever()
