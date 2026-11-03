# Maintaining Awesome Free AI Providers

A short handbook for maintainers. Contributors should read [contributing.md](../contributing.md) instead.

## What runs on its own

| Workflow | When | What it does | Where results go |
| --- | --- | --- | --- |
| [Review pull request](workflows/review.yml) | Every pull request, on open and on each push | Checks changed entries, loads their links, runs awesome-lint | One bot comment that updates in place, plus the `needs changes` or `ready for review` label |
| [List health](workflows/health.yml) | Mondays at 06:00 UTC, or by hand | Checks every entry and link, finds stale Verified dates and passed end dates | One `List health report` issue, opened, updated, or closed automatically |
| [Check main](workflows/check.yml) | Pushes to `main` that touch the README | Format checks and awesome-lint, no network | The workflow run (red if broken) |
| [Dependabot](dependabot.yml) | Monthly | Opens pull requests to update GitHub Actions versions | Pull requests |

Branch protection on `main` requires the `review` check from Review pull request to pass before a pull request can merge. Admins can still bypass it from the merge box or push to `main` directly. Change it under Settings, Branches.

Every check lives in one standard-library Python script, [scripts/review.py](scripts/review.py). Issue forms are in [ISSUE_TEMPLATE](ISSUE_TEMPLATE) and the pull request template is [pull_request_template.md](pull_request_template.md).

## Reviewing a pull request

1. Read the bot comment. `needs changes` means the contributor has something to fix, and GitHub keeps the merge button disabled; wait for a push. `ready for review` means the format is right and every link loads.
2. Open each source link in the changed entry and confirm the row says what the page says. This is the part the bot cannot do.
3. Check the judgment calls: the offer is live today, the operator is named in the terms, the provider is not a relay of closed models, and the section fits.
4. If the entry adds a token cap or a one-time token grant, update the table and totals in Combining Free Tiers and the two figures in the intro (or ask the contributor to).
5. Squash and merge with the pull request title as the commit message.

To rerun the bot after editing a pull request yourself, run the Review pull request workflow by hand with the pull request number.

## Handling issues

- **Suggestion** (`suggestion` label): check the source page against [What belongs here](../contributing.md#what-belongs-here). If it fits, add the entry yourself or ask the person to open a pull request. If not, close with the reason.
- **Update** (`entry update` label): open the linked source, edit the entry, set `Verified` to today, and close the issue from the pull request with `Fixes #123`.
- **List health report** (`maintenance` label): work through it from the top.
  - **Errors** are broken links, moved anchors, or format problems on `main`. Find the new section on the provider's site and update the link.
  - **Due for a re-check** lists entries whose `Verified` date is more than 90 days old, or whose stated end date has passed or is close. Re-check them as in [Updating an entry](../contributing.md#updating-an-entry), then tick them off.
  - The issue updates itself every Monday and closes itself when nothing is left.

## Warnings you can expect

Some providers' pages render with JavaScript or block automated requests. The bot reports them as warnings, never errors, and lists them in the workflow run summary rather than the issue. As of 2026-11-03 these were checked by hand in a browser:

- JavaScript-rendered: `aistudio.google.com`, `dataplatform.cloud.ibm.com`, `cloud.tencent.com.cn`, `platform.baichuan-ai.com`, `modelscope.cn`, and `aihorde.net/terms`.
- Blocked or redirected for automated requests: `scaleway.com` (HTTP 403) and `ovhcloud.com` (HTTP 307).

When a new provider has the same problem, add its host to `SOFT_HOSTS` in `scripts/review.py` after checking its anchors in a browser.

## Common changes

- **Add a section:** add the heading to README.md and Contents, add the name to `PROVIDER_SECTIONS` in `scripts/review.py`, and add it to the Section dropdown in `ISSUE_TEMPLATE/1-suggest-a-provider.yml`.
- **Change the re-check interval:** edit `STALE_DAYS` (90) in `scripts/review.py`.
- **Update the token estimate:** the intro gives two figures, recurring and one-time, and Combining Free Tiers shows how they add up. Count only token caps and token grants that the provider publishes; leave out request caps, console-only limits, dollar credits, and embedding grants.

## Running checks yourself

```sh
python3 .github/scripts/review.py format README.md          # align table pipes
python3 .github/scripts/review.py check README.md           # format, order, duplicates, dates
python3 .github/scripts/review.py check README.md --network # also load every link and anchor
python3 .github/scripts/review.py full README.md            # what Monday's health job sees, without opening an issue
```
