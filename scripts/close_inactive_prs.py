"""Close MirrorWeb pull requests after 90 days without an update."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess


def github(endpoint, *, paginate=False, close=False):
    command = ["gh", "api", endpoint]
    if paginate:
        command += ["--paginate", "--slurp"]
    if close:
        command += ["--method", "PATCH", "-f", "state=closed"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def close_inactive_prs(repositories, cutoff, *, apply=False, api=github):
    records = []
    for repository in repositories:
        name = repository["full_name"]
        if repository["owner"]["login"].lower() != "mirrorweb" or repository["archived"]:
            continue
        print(f"Scanning {name}", flush=True)
        try:
            # Collect pages before any mutation, so closing PRs cannot shift pages.
            pages = api(f"repos/{name}/pulls?state=open&sort=updated&direction=asc&per_page=100", paginate=True)
            candidates = [pr for page in pages for pr in page if timestamp(pr["updated_at"]) < cutoff]
            for candidate in candidates:
                endpoint = f"repos/{name}/pulls/{candidate['number']}"
                pr = api(endpoint)
                record = {"url": pr["html_url"], "updated_at": pr["updated_at"]}
                if pr["state"] != "open" or timestamp(pr["updated_at"]) >= cutoff:
                    record["result"] = "skipped_changed"
                elif not apply:
                    record["result"] = "would_close"
                elif api(f"repos/{name}")["archived"]:
                    record["result"] = "skipped_archived"
                else:
                    closed = api(endpoint, close=True)
                    if closed["state"] != "closed" or closed["merged"]:
                        raise RuntimeError(f"Closure was not confirmed for {pr['html_url']}")
                    record["result"] = "closed"
                records.append(record)
                print(json.dumps(record), flush=True)
        except (subprocess.CalledProcessError, RuntimeError) as error:
            # Continue other repositories, but fail the run after saving the report.
            detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            records.append({"repository": name, "result": "error", "detail": detail})
            print(f"Failed to process {name}", flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Close PRs. Without this flag, only report candidates.")
    parser.add_argument("--repositories-file", type=Path, help="Repository inventory for local preview only.")
    args = parser.parse_args()
    if args.apply and args.repositories_file:
        parser.error("--repositories-file is only supported in preview mode")
    if args.repositories_file:
        repositories = json.loads(args.repositories_file.read_text())
    else:
        pages = github("installation/repositories?per_page=100", paginate=True)
        repositories = [repository for page in pages for repository in page["repositories"]]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
    records = close_inactive_prs(repositories, cutoff, apply=args.apply)
    report = {"cutoff": cutoff.isoformat(), "apply": args.apply, "repositories_visible": len(repositories), "results": records}
    Path("inactive-pr-report.json").write_text(json.dumps(report, indent=2) + "\n")
    counts = {result: sum(record["result"] == result for record in records)
              for result in sorted({record["result"] for record in records})}
    summary = f"Mode: {'close' if args.apply else 'preview'}\n\nCutoff: {cutoff.isoformat()}\n\nRepositories visible: {len(repositories)}\n\nResults: {json.dumps(counts)}\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write(summary)
    if counts.get("error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
