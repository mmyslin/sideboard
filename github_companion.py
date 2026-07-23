#!/usr/bin/env python3
"""VibeMap ⇄ GitHub companion — read path (Phase 1).

Syncs GitHub issues into roadmap.json (the file the board polls) and serves the
board. GitHub Issues are the source of truth; the swimlane split (backlog vs
in_progress) and ordering live in a local sidecar (.vibemap/meta.json).
done == closed issue. See docs/github-sync-design.md.

Env:
  VIBEMAP_REPO           owner/name (default: gh's current repo)
  VIBEMAP_PORT           default 7777
  VIBEMAP_SYNC_SECONDS   re-sync interval, default 45
"""
import json, os, sys, subprocess, threading, time, datetime, http.server, socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(HERE, ".vibemap", "meta.json")
BOARD_PATH = os.path.join(HERE, "roadmap.json")
REPO = os.environ.get("VIBEMAP_REPO")
PORT = int(os.environ.get("VIBEMAP_PORT", "7777"))
SYNC_SECONDS = int(os.environ.get("VIBEMAP_SYNC_SECONDS", "45"))
COLUMNS = ("backlog", "in_progress", "done")  # done is derived from closed state


def fetch_issues():
    cmd = ["gh", "issue", "list", "--state", "all", "--limit", "1000",
           "--json", "number,title,body,state"]
    if REPO:
        cmd += ["--repo", REPO]
    return json.loads(subprocess.check_output(cmd, text=True))


def load_meta():
    try:
        with open(META_PATH) as f:
            m = json.load(f)
    except FileNotFoundError:
        m = {}
    return {"status": dict(m.get("status", {})), "order": [str(n) for n in m.get("order", [])]}


def save_meta(meta):
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def reconcile(issues, meta):
    """GitHub wins for existence + open/closed; sidecar wins for backlog/in_progress + order."""
    status = dict(meta["status"])
    order = list(meta["order"])
    present = {str(i["number"]) for i in issues}
    for i in issues:
        n = str(i["number"])
        if i["state"].lower() == "open" and n not in status:
            status[n] = "backlog"          # new open issue defaults to Backlog
    status = {n: s for n, s in status.items() if n in present}   # drop vanished issues
    order = [n for n in order if n in present]
    for i in issues:                        # append any new numbers to the rank
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
        items.append({
            "ref": int(n),
            "id": f"gh-{n}",
            "title": i["title"],
            "notes": i.get("body") or "",
            "status": "done" if closed else meta["status"].get(n, "backlog"),
        })
    return {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }


def sync():
    issues = fetch_issues()
    meta = reconcile(issues, load_meta())
    save_meta(meta)
    board = build_board(issues, meta)
    with open(BOARD_PATH, "w") as f:
        json.dump(board, f, indent=2, ensure_ascii=False)
    return len(board["items"])


def sync_loop():
    while True:
        time.sleep(SYNC_SECONDS)
        try:
            print(f"[vibemap] synced {sync()} items from GitHub", flush=True)
        except Exception as e:
            print(f"[vibemap] sync error: {e}", file=sys.stderr, flush=True)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    os.chdir(HERE)
    with socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler) as httpd:
        print(f"[vibemap] serving {HERE} at http://127.0.0.1:{PORT}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    try:
        print(f"[vibemap] initial sync: {sync()} items", flush=True)
    except Exception as e:
        print(f"[vibemap] initial sync failed: {e}", file=sys.stderr, flush=True)
    threading.Thread(target=sync_loop, daemon=True).start()
    serve()
