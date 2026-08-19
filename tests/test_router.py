#!/usr/bin/env python3
"""Sideboard router tests — pure sidecar/reconcile logic plus a live token-gating
integration pass. No network, no `gh`: unit tests exercise the Project methods
directly with a temp sidecar, and the integration test spawns the router and hits
only the endpoints that don't call gh (healthz, token-gated reads, body cap).

Run: python3 -m unittest discover -s tests -v   (stdlib only, no pytest needed).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER = os.path.join(REPO, "scripts", "sideboard_router.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("sbr", ROUTER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)          # safe: server only starts under __main__
    return m


sbr = _load_module()


def _project_with_sidecar(content):
    """A Project bound to a temp sidecar, bypassing __init__ (no gh repo detect)."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".sideboard"))
    with open(os.path.join(d, ".sideboard", "meta.json"), "w") as f:
        f.write(content)
    p = sbr.Project.__new__(sbr.Project)
    p.path = d
    p.meta_path = os.path.join(d, ".sideboard", "meta.json")
    p.error = None
    return p


def _quarantined(p):
    return os.path.exists(p.meta_path + ".corrupt.bak")


class WrongShapeSidecarQuarantine(unittest.TestCase):
    """#137: valid-JSON-but-wrong-shape sidecars must quarantine, never raise."""

    def test_schema_null_migrate_quarantines(self):
        p = _project_with_sidecar('{"schema": null}')
        p.migrate()                                  # must not raise
        self.assertTrue(_quarantined(p))

    def test_top_level_array_migrate_quarantines(self):
        p = _project_with_sidecar('[1, 2, 3]')
        p.migrate()
        self.assertTrue(_quarantined(p))

    def test_status_list_load_quarantines(self):
        p = _project_with_sidecar('{"schema": 2, "status": [1, 2, 3]}')
        meta = p._load_meta()                        # must not raise
        self.assertEqual(meta["status"], {})
        self.assertTrue(_quarantined(p))

    def test_non_numeric_status_key_save_quarantines(self):
        p = _project_with_sidecar('{"schema": 2}')
        p._save_meta({"status": {"abc": "backlog"}, "order": [],
                      "tag_colors": {}, "next_color": 0, "sequences": []})
        self.assertTrue(_quarantined(p))

    def test_valid_sidecar_round_trips_untouched(self):
        p = _project_with_sidecar(
            '{"schema": 2, "status": {"5": "backlog"}, "order": ["5"],'
            ' "tag_colors": {}, "next_color": 0, "sequences": []}')
        meta = p._load_meta()
        p.migrate()
        p._save_meta(meta)
        with open(p.meta_path) as f:
            back = json.load(f)
        self.assertEqual(back["status"], {"5": "backlog"})
        self.assertEqual(back["order"], ["5"])
        self.assertFalse(_quarantined(p))


class Reconcile(unittest.TestCase):
    """#112/#76: prune rules for the sidecar-vs-GitHub reconcile."""

    def _p(self):
        return _project_with_sidecar('{"schema": 2}')

    def test_empty_fetch_never_prunes(self):
        p = self._p()
        meta = {"status": {"1": "in_progress", "2": "backlog"}, "order": ["1", "2"],
                "tag_colors": {}, "next_color": 0, "sequences": []}
        out = p._reconcile([], meta, complete=True)   # zero-issue fetch
        self.assertEqual(out["status"], {"1": "in_progress", "2": "backlog"})
        self.assertEqual(out["order"], ["1", "2"])

    def test_complete_nonempty_fetch_prunes_missing(self):
        p = self._p()
        meta = {"status": {"1": "backlog", "2": "backlog"}, "order": ["1", "2"],
                "tag_colors": {}, "next_color": 0, "sequences": []}
        issues = [{"number": 1, "state": "open", "labels": []}]   # #2 is gone
        out = p._reconcile(issues, meta, complete=True)
        self.assertIn("1", out["status"])
        self.assertNotIn("2", out["status"])

    def test_incomplete_fetch_never_prunes(self):
        p = self._p()
        meta = {"status": {"1": "backlog", "2": "backlog"}, "order": ["1", "2"],
                "tag_colors": {}, "next_color": 0, "sequences": []}
        issues = [{"number": 1, "state": "open", "labels": []}]   # page-limited
        out = p._reconcile(issues, meta, complete=False)
        self.assertIn("2", out["status"])            # not treated as deleted

    def test_new_open_issue_lands_in_backlog(self):
        p = self._p()
        meta = {"status": {}, "order": [], "tag_colors": {}, "next_color": 0, "sequences": []}
        out = p._reconcile([{"number": 9, "state": "open", "labels": []}], meta, complete=True)
        self.assertEqual(out["status"].get("9"), "backlog")


class NormSequences(unittest.TestCase):
    """_norm_sequences must coerce hostile shapes without raising."""

    def test_non_dict_members_dropped(self):
        out = sbr._norm_sequences([{"id": "a", "title": "T", "items": [1, 2]}, "junk", 5, None])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["items"], ["1", "2"])

    def test_none_is_empty(self):
        self.assertEqual(sbr._norm_sequences(None), [])

    def test_items_deduped_and_stringified(self):
        out = sbr._norm_sequences([{"id": "a", "title": "", "items": [3, 3, "3", 4]}])
        self.assertEqual(out[0]["items"], ["3", "4"])


class LiveTokenGating(unittest.TestCase):
    """Integration: spawn the router (no gh needed for these endpoints) and check
    the auth surface — #111 read-gating, #148 healthz title, #147 body cap."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.home, ".claude"))
        cls.port = 7899
        env = dict(os.environ, HOME=cls.home, SIDEBOARD_PORT=str(cls.port))
        cls.proc = subprocess.Popen([sys.executable, ROUTER], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(50):
            try:
                urllib.request.urlopen(cls.base + "/healthz", timeout=1).read()
                break
            except Exception:
                time.sleep(0.1)
        cls.token = open(os.path.join(cls.home, ".claude", "sideboard-token")).read().strip()

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except Exception:
            cls.proc.kill()

    def _get(self, path, token=None):
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("X-Sideboard-Token", token)
        try:
            r = urllib.request.urlopen(req, timeout=3)
            return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_healthz_open(self):
        code, body = self._get("/healthz")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["router"])

    def test_healthz_hides_title_without_token(self):          # #148
        _, body = self._get("/healthz")
        self.assertNotIn("active", json.loads(body))
        _, body2 = self._get("/healthz", token=self.token)
        self.assertIn("active", json.loads(body2))

    def test_roadmap_json_requires_token(self):                # #111
        self.assertEqual(self._get("/roadmap.json")[0], 403)
        self.assertEqual(self._get("/roadmap.json", token=self.token)[0], 200)

    def test_projects_requires_token(self):                    # #111
        self.assertEqual(self._get("/projects")[0], 403)
        self.assertEqual(self._get("/projects", token=self.token)[0], 200)

    def test_wrong_token_rejected(self):
        self.assertEqual(self._get("/roadmap.json", token="deadbeef")[0], 403)

    def test_board_shell_open(self):
        code, body = self._get("/roadmap-board.html")
        self.assertEqual(code, 200)
        self.assertIn("<html", body.lower())

    def test_negative_content_length_rejected(self):           # #147
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        c.putrequest("POST", "/api/drop", skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", f"127.0.0.1:{self.port}")
        c.putheader("Origin", self.base)
        c.putheader("X-Sideboard-Token", self.token)
        c.putheader("Content-Length", "-100")
        c.endheaders()
        c.send(b"{}")
        self.assertEqual(c.getresponse().status, 413)


if __name__ == "__main__":
    unittest.main(verbosity=2)
