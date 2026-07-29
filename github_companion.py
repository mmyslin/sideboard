#!/usr/bin/env python3
"""VibeMap ⇄ GitHub companion — read + local writes (Phases 1–2).

GitHub Issues are the source of truth. The swimlane split (backlog vs
in_progress) and card order live in a local sidecar (.vibemap/meta.json).
done == closed issue. See docs/github-sync-design.md.

Serves the board and exposes POST /api/drop for move+reorder:
  - move within Backlog/In Progress or reorder → sidecar only (no GitHub call)
  - move to Done → gh issue close;  move out of Done → gh issue reopen

Env: VIBEMAP_REPO (owner/name), VIBEMAP_PORT (7777), VIBEMAP_SYNC_SECONDS (45)
"""
import json, os, sys, subprocess, threading, time, datetime, http.server, socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(HERE, ".vibemap", "meta.json")
BOARD_PATH = os.path.join(HERE, "roadmap.json")
REPO = os.environ.get("VIBEMAP_REPO")
PORT = int(os.environ.get("VIBEMAP_PORT", "7777"))
SYNC_SECONDS = int(os.environ.get("VIBEMAP_SYNC_SECONDS", "45"))

LOCK = threading.RLock()
STATE = {"issues": []}   # last-fetched issues, for local regenerates without re-hitting GitHub


# ---- GitHub (via gh) --------------------------------------------------------
def _gh(*args):
    cmd = ["gh", *args] + (["--repo", REPO] if REPO else [])
    return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout


def fetch_issues():
    return json.loads(_gh("issue", "list", "--state", "all", "--limit", "1000",
                          "--json", "number,title,body,state"))


def gh_close(n):  subprocess.check_call(["gh", "issue", "close", str(n)] + (["--repo", REPO] if REPO else []), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def gh_reopen(n): subprocess.check_call(["gh", "issue", "reopen", str(n)] + (["--repo", REPO] if REPO else []), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gh_create(title, body):
    cmd = ["gh", "issue", "create", "--title", title, "--body", body or ""] + (["--repo", REPO] if REPO else [])
    url = subprocess.run(cmd, check=True, text=True, capture_output=True).stdout.strip().splitlines()[-1]
    return int(url.rsplit("/", 1)[-1])


def gh_edit(n, title, body):
    subprocess.run(["gh", "issue", "edit", str(n), "--title", title, "--body", body or ""]
                   + (["--repo", REPO] if REPO else []), check=True, text=True, capture_output=True)


# ---- sidecar + merge --------------------------------------------------------
def load_meta():
    try:
        m = json.load(open(META_PATH))
    except FileNotFoundError:
        m = {}
    return {"status": dict(m.get("status", {})), "order": [str(n) for n in m.get("order", [])]}


def save_meta(meta):
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    # deterministic output (status sorted by issue number) so periodic rewrites don't churn git
    stable = {"status": {k: meta["status"][k] for k in sorted(meta["status"], key=int)},
              "order": meta["order"]}
    json.dump(stable, open(META_PATH, "w"), indent=2)


def reconcile(issues, meta):
    """GitHub wins for existence + open/closed; sidecar wins for backlog/in_progress + order."""
    status, order = dict(meta["status"]), list(meta["order"])
    present = {str(i["number"]) for i in issues}
    for i in issues:
        n = str(i["number"])
        if i["state"].lower() == "open" and n not in status:
            status[n] = "backlog"
    status = {n: s for n, s in status.items() if n in present}
    order = [n for n in order if n in present]
    for i in issues:
        n = str(i["number"])
        if n not in order:
            order.append(n)
    return {"status": status, "order": order}


def build_board(issues, meta):
    by_num = {str(i["number"]): i for i in issues}
    items = []
    for n in meta["order"]:
        i = by_num.get(n)
        if not i:
            continue
        closed = i["state"].lower() == "closed"
        items.append({"ref": int(n), "id": f"gh-{n}", "title": i["title"],
                      "notes": i.get("body") or "",
                      "status": "done" if closed else meta["status"].get(n, "backlog")})
    return {"updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": items}


def _write(issues):
    meta = reconcile(issues, load_meta())
    save_meta(meta)
    json.dump(build_board(issues, meta), open(BOARD_PATH + ".tmp", "w"), indent=2, ensure_ascii=False)
    os.replace(BOARD_PATH + ".tmp", BOARD_PATH)   # atomic: board never reads a half-written file
    return len(meta["order"])


def sync():
    """Full sync: re-fetch from GitHub, then regenerate."""
    with LOCK:
        STATE["issues"] = fetch_issues()
        return _write(STATE["issues"])


def regenerate():
    """Local regenerate using cached issues (no GitHub round-trip)."""
    with LOCK:
        return _write(STATE["issues"])


def apply_drop(number, status, order):
    """Move a card to `status` and set the global `order`."""
    n = str(number)
    with LOCK:
        issue = next((i for i in STATE["issues"] if str(i["number"]) == n), None)
        closed = bool(issue) and issue["state"].lower() == "closed"
        meta = load_meta()
        did_gh = False
        if status == "done":
            if issue and not closed:
                gh_close(n); did_gh = True
            meta["status"].pop(n, None)          # done is derived from closed
        elif status in ("backlog", "in_progress"):
            if closed:
                gh_reopen(n); did_gh = True
            meta["status"][n] = status
        if order:
            meta["order"] = [str(x) for x in order]
        save_meta(meta)
    return sync() if did_gh else regenerate()    # re-fetch only when GitHub state changed


def create_issue(title, body):
    n = gh_create(title, body)   # new open issue -> reconcile lands it in Backlog
    sync()
    return n


def edit_issue(n, title, body):
    gh_edit(n, title, body)
    sync()


# ---- HTTP -------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # always serve the latest board on reload
        super().end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            if path == "/api/drop":
                apply_drop(body["number"], body["status"], body.get("order"))
                resp = {"ok": True}
            elif path == "/api/create":
                resp = {"ok": True, "number": create_issue(body["title"], body.get("notes", ""))}
            elif path == "/api/edit":
                edit_issue(body["number"], body["title"], body.get("notes", ""))
                resp = {"ok": True}
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
        except Exception as e:
            print(f"[vibemap] POST {path} error: {e}", file=sys.stderr, flush=True)
            self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())


def sync_loop():
    while True:
        time.sleep(SYNC_SECONDS)
        try:
            print(f"[vibemap] synced {sync()} items", flush=True)
        except Exception as e:
            print(f"[vibemap] sync error: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    os.chdir(HERE)
    try:
        print(f"[vibemap] initial sync: {sync()} items", flush=True)
    except Exception as e:
        print(f"[vibemap] initial sync failed: {e}", file=sys.stderr, flush=True)
    threading.Thread(target=sync_loop, daemon=True).start()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"[vibemap] serving {HERE} at http://127.0.0.1:{PORT}", flush=True)
        httpd.serve_forever()
