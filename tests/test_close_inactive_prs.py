import datetime as dt
import importlib.util
from pathlib import Path
import subprocess
import unittest


spec = importlib.util.spec_from_file_location(
    "close_inactive_prs", Path(__file__).parents[1] / "scripts" / "close_inactive_prs.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CUTOFF = dt.datetime(2026, 7, 28, tzinfo=dt.timezone.utc)


def repository(name="mirrorweb/example", archived=False):
    return {"full_name": name, "owner": {"login": name.split("/")[0]}, "archived": archived}


def pr(number, updated_at="2026-07-27T00:00:00Z", **fields):
    return {"number": number, "html_url": f"https://github.com/mirrorweb/example/pull/{number}",
            "updated_at": updated_at, "state": "open", "merged": False, **fields}


class ClosureTests(unittest.TestCase):
    def test_closes_inactive_drafts_but_preserves_recent_and_boundary_prs(self):
        draft = pr(1, draft=True)
        boundary = pr(2, "2026-07-28T00:00:00Z")
        recent = pr(3, "2026-10-25T00:00:00Z")
        changed = pr(4)
        already_closed = pr(5)
        calls = []

        def api(endpoint, **options):
            calls.append((endpoint, options))
            if options.get("paginate"):
                return [[draft, boundary], [recent, changed, already_closed]]
            if endpoint.endswith("/pulls/4"):
                return pr(4, "2026-10-26T00:00:00Z")
            if endpoint.endswith("/pulls/5"):
                return pr(5, state="closed")
            if endpoint == "repos/mirrorweb/example":
                return repository()
            return pr(1, state="closed" if options.get("close") else "open", draft=True)

        records = module.close_inactive_prs([repository()], CUTOFF, apply=True, api=api)
        self.assertEqual([r["result"] for r in records], ["closed", "skipped_changed", "skipped_changed"])
        self.assertEqual([endpoint for endpoint, options in calls if options.get("close")],
                         ["repos/mirrorweb/example/pulls/1"])

    def test_preview_has_no_mutations(self):
        def api(endpoint, **options):
            self.assertFalse(options.get("close"))
            return [[pr(1)]] if options.get("paginate") else pr(1)

        records = module.close_inactive_prs([repository()], CUTOFF, api=api)
        self.assertEqual(records[0]["result"], "would_close")

    def test_excludes_archived_and_other_organizations(self):
        def api(*args, **kwargs):
            self.fail("Excluded repositories must not be scanned")

        records = module.close_inactive_prs(
            [repository(archived=True), repository("other/example")], CUTOFF, apply=True, api=api
        )
        self.assertEqual(records, [])

    def test_repository_archived_during_scan_is_not_mutated(self):
        def api(endpoint, **options):
            self.assertFalse(options.get("close"))
            if options.get("paginate"):
                return [[pr(1)]]
            if endpoint == "repos/mirrorweb/example":
                return repository(archived=True)
            return pr(1)

        records = module.close_inactive_prs([repository()], CUTOFF, apply=True, api=api)
        self.assertEqual(records[0]["result"], "skipped_archived")

    def test_failure_is_recorded_and_other_repositories_continue(self):
        def api(endpoint, **options):
            if "broken" in endpoint:
                raise subprocess.CalledProcessError(403, ["gh", "api"], stderr="Forbidden")
            return [[pr(1)]] if options.get("paginate") else pr(1)

        records = module.close_inactive_prs(
            [repository("mirrorweb/broken"), repository()], CUTOFF, api=api
        )
        self.assertEqual([r["result"] for r in records], ["error", "would_close"])

    def test_unconfirmed_close_is_an_error(self):
        def api(endpoint, **options):
            if options.get("paginate"):
                return [[pr(1)]]
            return repository() if endpoint == "repos/mirrorweb/example" else pr(1)

        records = module.close_inactive_prs([repository()], CUTOFF, apply=True, api=api)
        self.assertEqual(records[0]["result"], "error")


if __name__ == "__main__":
    unittest.main()
