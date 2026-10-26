# Enable automatic closure of inactive PRs

This repository runs a daily check at 06:23 UTC across the MirrorWeb repositories available to the GitHub App. The check closes open PRs, including drafts, when GitHub's `updated_at` timestamp is more than 90 days old. Archived repositories are excluded. Branches are retained. No comments or labels are added.

Any activity that changes GitHub's PR `updated_at` timestamp restarts the inactivity period. The script reads each candidate again before closing it. GitHub does not support a conditional close tied to that timestamp, so activity between the final read and the close can still race with the workflow.

## Create and install the App

1. Open the MirrorWeb organization settings, then **Developer settings → GitHub Apps → New GitHub App**.
2. Name the App `MirrorWeb inactive PR closer`, or choose another available name. Use this repository's URL for the homepage.
3. Disable **Active** under Webhook. The workflow runs on a schedule and does not need webhooks or user authorization.
4. Set the repository permission **Pull requests** to **Read and write**. GitHub includes **Metadata: Read-only** automatically. Leave other permissions unset.
5. Restrict installation to this account, then create the App.
6. Install the App on the `mirrorweb` organization and select **All repositories**. This covers existing and future repositories. A selected-repository installation only scans the selected repositories.
7. On the App settings page, generate a private key and note the App ID.
8. In this repository's **Settings → Secrets and variables → Actions**, add the repository variable `STALE_PR_APP_ID` with the App ID and the repository secret `STALE_PR_APP_PRIVATE_KEY` with the complete downloaded PEM file. Do not commit the key.

## Activate and verify

1. Merge the workflow into the default branch. Scheduled workflows only run from that branch.
2. Open **Actions → Close inactive PRs across MirrorWeb → Run workflow**. Leave **Preview candidates without closing PRs** selected.
3. Check the repository count and candidate list in the run summary. Confirm that the App installation covers all repositories.
4. Run the workflow again with the preview checkbox cleared to close matching PRs immediately. Subsequent daily runs close matching PRs automatically.

The workflow reports missing App configuration as an error. Repository failures are recorded in the summary and fail the run after the remaining repositories have been processed. Disable this workflow in Actions to stop automatic closures.

## Run a local preview

Use an authenticated GitHub CLI session to save the organization's repository inventory, then preview:

```sh
gh api --paginate 'orgs/mirrorweb/repos?per_page=100' --jq '.[]' | jq -s '.' > /tmp/mirrorweb-repositories.json
python3 scripts/close_inactive_prs.py --repositories-file /tmp/mirrorweb-repositories.json
```

This command writes `inactive-pr-report.json` and does not close PRs. In GitHub Actions, the script uses the App installation's paginated inventory directly and does not use search results.

Run the selection and closure tests with `python3 -m unittest discover -s tests`.
