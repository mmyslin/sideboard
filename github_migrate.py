#!/usr/bin/env python3
"""One-time migration: current roadmap.json items -> GitHub issues + sidecar.

DRY-RUN by default (prints the plan, touches nothing). Pass --commit to actually
create issues. Idempotency is NOT guaranteed — run once. See docs/github-sync-design.md.

  python3 github_migrate.py            # show the plan
  python3 github_migrate.py --commit   # create the issues for real
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROADMAP = os.path.join(HERE, "roadmap.json")
META_PATH = os.path.join(HERE, ".vibemap", "meta.json")
GITIGNORE = os.path.join(HERE, ".gitignore")
REPO = os.environ.get("VIBEMAP_REPO")


def create_issue(title, body):
    cmd = ["gh", "issue", "create", "--title", title, "--body", body or ""]
    if REPO:
        cmd += ["--repo", REPO]
    url = subprocess.check_output(cmd, text=True).strip().splitlines()[-1]
    return int(url.rsplit("/", 1)[-1])


def close_issue(num):
    cmd = ["gh", "issue", "close", str(num)]
    if REPO:
        cmd += ["--repo", REPO]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL)


def main(commit):
    items = json.load(open(ROADMAP))["items"]
    print(f"{'MIGRATING' if commit else 'DRY RUN —'} {len(items)} items -> GitHub issues"
          f"{' in '+REPO if REPO else ''}\n")
    status, order = {}, []
    for it in items:
        title, st = it["title"], it.get("status", "backlog")
        if commit:
            num = create_issue(title, it.get("notes", ""))
            if st == "done":
                close_issue(num)
            print(f"  #{num}  [{st:11}] {title}")
        else:
            print(f"  (new) [{st:11}] {title}")
            num = None
        if num is not None:
            order.append(str(num))
            if st in ("backlog", "in_progress"):   # done is derived from closed
                status[str(num)] = st
    if not commit:
        print("\nDry run — nothing created. Re-run with --commit to migrate.")
        return
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    json.dump({"status": status, "order": order}, open(META_PATH, "w"), indent=2)
    # roadmap.json is now a generated artifact
    lines = open(GITIGNORE).read().splitlines() if os.path.exists(GITIGNORE) else []
    if "roadmap.json" not in lines:
        open(GITIGNORE, "a").write("roadmap.json\n")
    print(f"\nDone. Wrote {META_PATH}, gitignored roadmap.json.")
    print("Next: stop `python -m http.server`, run `python3 github_companion.py`.")


if __name__ == "__main__":
    main("--commit" in sys.argv)
