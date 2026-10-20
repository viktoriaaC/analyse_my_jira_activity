# Plan: Jira activity CLI (Python)

## Context
The repo is empty apart from `CLAUDE.md`. The goal is a Python CLI that takes a Jira Cloud site, credentials and a date range. It calls the Jira REST API and shows two things in the terminal:
1. a visual timeline of which statuses each ticket was in during the period
2. which tickets were in each status during the period

Decisions made: **Jira Cloud** (email + API token, REST v3). **Tickets assigned to the user** during the range. **Terminal output with `rich`**. Approved dependencies are `requests`, `typer` (click), `keyring`, and `pytest` (dev only).

Rules from CLAUDE.md:
- all I/O lives in one layer
- every external call has its own error with a unique message
- one job per function
- clear CLI usage docs
- logging only through `utils/logger.py`
- nothing is saved without asking
- work only on a feature branch; `main` changes only through a PR

## Branch
`feature/jira-activity-cli`. Open a PR to `main` at the end and do not merge it.

## Project layout
```
pyproject.toml                 # package metadata, deps, console script "jira-activity"
README.md                      # install + usage guide (the "clear CLI description")
src/jira_activity/
  __init__.py
  cli.py                       # typer app: parses args, wires layers, maps errors → exit codes
  errors.py                    # JiraActivityError base + one subclass per failure, each with unique code/message
  domain/                      # PURE logic, no I/O
    models.py                  # dataclasses: Issue, StatusChange, StatusInterval, DateRange
    timeline.py                # build status intervals from changelog; clip to date range
    aggregate.py               # time-per-status totals; status → tickets mapping
  adapters/                    # ALL I/O lives here
    jira_client.py             # HTTP calls to Jira (requests), pagination, response parsing
    credentials.py             # keyring read/write, env var lookup, hidden prompt
    renderer.py                # rich tables + text Gantt timeline
  utils/
    logger.py                  # the single logging config; never logs tokens or response bodies
tests/
  test_timeline.py, test_aggregate.py, test_jira_client.py (mocked HTTP), test_cli.py (typer CliRunner)
```

## CLI design (needs your approval, since it is the public interface)
```
jira-activity configure --site https://acme.atlassian.net --email me@acme.se
    → asks for the token (hidden input), then asks "Save site, email and token in the OS keychain? [y/N]"

jira-activity report --from 2026-09-01 --to 2026-09-30
    [--site URL] [--email EMAIL] [--token TOKEN]   (otherwise taken from env, then keyring, then a prompt)
    [--project KEY]                                (optional JQL narrowing)
    [--verbose]                                    (debug logging to stderr: method, path, status code only)
```
- Credentials are looked up in this order: CLI flag → env vars `JIRA_SITE` / `JIRA_EMAIL` / `JIRA_API_TOKEN` → keyring → interactive prompt.
- Site, email and token are only saved if the user says yes in `configure`.
  - They are saved only in the OS keychain (service `jira-activity`), never in a plain file.
  - The token is saved per email, as `api-token:<email>`.
- `configure` does not check the credentials against Jira. A wrong token shows up on the next `report` as JA-101.

## Core flow
1. **cli.report** checks the dates (`from <= to`, ISO format, using `models.parse_day`) and builds a `DateRange`.
   - Days start and end in the computer's local timezone at run time.
   - Across a daylight-saving change, the hours near the change can be off by one.
2. **jira_client.search_issues** calls `GET /rest/api/3/search/jql` with this JQL:
   `assignee was currentUser() DURING ("<from>", "<to>")` (plus `AND project = "X"` if given, quoted safely).
   - The search covers one extra day on each side of the range, because JQL reads dates in the Jira profile's timezone. Step 5 clips the extra time away.
   It requests the fields `summary,status,created`. Pagination uses `nextPageToken`.
3. **jira_client.fetch_changelog(key)** calls `GET /rest/api/3/issue/{key}/changelog` with `startAt`/`isLast` pagination. It keeps only items where `field == "status"`.
4. **timeline.build_intervals(issue, changes)** works out the status periods:
   - start at `created`, in the first change's `fromString`, or in the current status if there are no changes
   - each change closes one interval and opens the next
   - the last interval stays open until "now"
5. **timeline.clip(intervals, range)** cuts the intervals to the requested range and drops empty ones.
6. **aggregate.time_per_status**, **aggregate.tickets_per_status** and **aggregate.hours_per_ticket_status** are pure functions.
   - `hours_per_ticket_status` adds up the clipped interval durations for each (ticket, status) pair.
   - It returns `dict[issue_key, dict[status, float_hours]]`, rounded to 0.1 h.
   - Hours are calendar hours, not working hours.
   - If a ticket goes back into a status, the time is added to that status's total.
7. **renderer** prints four things:
   - (a) a summary table: status → total hours and number of tickets
   - (b) one Gantt row per ticket, with coloured segments over the date axis and a status legend
   - (c) a status → ticket list table (key + summary + hours in status)
   - (d) **an hours-per-status matrix**:
     - one row per ticket (key + summary) and one column per status seen in the period
     - each cell shows hours, e.g. `12.5`, or `–` if the ticket was never in that status
     - a final "Total h" column shows each ticket's total
     - a footer row shows the total for each status
   - Status columns and rows follow the order in which statuses first appear (`aggregate.status_order`). That usually matches the workflow.
   - The timeline uses one character per time slice, coloured by the status at the middle of the slice (`timeline.status_at`). A very short status can disappear from the bar. The hours tables are always exact.
   - The footer totals add up the rounded cells, so the table always sums correctly on screen.

## Error handling (`errors.py`, unique code per case)
| Code | Exception | Trigger |
|---|---|---|
| JA-101 | `JiraAuthError` | HTTP 401: wrong email or token |
| JA-102 | `JiraPermissionError` | HTTP 403 |
| JA-103 | `JiraNotFoundError` | HTTP 404: wrong site URL or issue |
| JA-104 | `JiraRateLimitError` | HTTP 429 after retries (respect `Retry-After`, max 3) |
| JA-105 | `JiraServerError` | HTTP 5xx |
| JA-106 | `JiraConnectionError` | `requests.ConnectionError` / SSL error |
| JA-107 | `JiraTimeoutError` | `requests.Timeout` (timeout 30 s) |
| JA-108 | `JiraResponseFormatError` | invalid JSON or missing expected keys |
| JA-109 | `JiraBadRequestError` | HTTP 400, for example bad JQL or an unknown project. The error includes Jira's own message. |
| JA-110 | `JiraUnexpectedStatusError` | any other non-2xx status code |
| JA-201 | `InvalidDateRangeError` | bad format or from > to |
| JA-202 | `InvalidSiteUrlError` | not https / not parseable |
| JA-301 | `CredentialStoreError` | keyring backend failure |
| JA-302 | `MissingCredentialsError` | no token found and not interactive |

`cli.py` catches `JiraActivityError` and prints `[code] message` in red on stderr. Unexpected exceptions get a generic JA-999 message that names the exception type.

Exit codes:
| Code | Meaning |
|---|---|
| 0 | success |
| 1 | an error was shown as `[JA-xxx]` |
| 2 | wrong command usage, reported by typer |
| 130 | cancelled with Ctrl+C |

## Logging
`utils/logger.py` sets up one `logging` logger, set to WARNING by default. `report --verbose` switches it to DEBUG; `configure` has no `--verbose`. It logs only the endpoint path and status code. It never logs the token, auth headers or response bodies, and it never writes to a file.

## Status
- Part 1 is done (`71c8509`).
- Part 2 is done (`d439341`). It has 21 passing tests.
- Part 3 is done (`1ea48e3`). It has 37 new tests, so 58 tests pass in total.
  - It added JA-109 and JA-110 to the error table.
- Part 4 is done (`d001c02`). It has 20 new tests, so 78 tests pass in total.
- Part 5 is done (`0b45fb2`). It has 19 new tests, so 97 tests pass in total.
  - Part 6 later fixed a renderer bug: rich read `[...]` in Jira data as markup, so all Jira data is now passed as `Text`.
- Part 6 is done. It has 26 new tests, so 123 tests pass in total.
  - typer's tab-completion options are turned off, so the CLI matches the approved design.
  - Progress is shown with a spinner on stderr.
- `--verbose` on `report` was approved by the user on 2026-10-20.
- Optional integration tests against a real Jira site were declined by the user. Real Jira is checked only by a manual run.
- Next: part 7 (`README.md` and a pull request). Also add the `readme` line back to `pyproject.toml`.

## Implementation order
1. Branch, `pyproject.toml`, package skeleton, `utils/logger.py`, `errors.py`
2. `domain/` models, timeline and aggregate, with unit tests (the trickiest logic)
3. `adapters/jira_client.py` with tests using mocked `requests`
4. `adapters/credentials.py`
5. `adapters/renderer.py`
6. `cli.py`, wiring everything with CliRunner tests
7. `README.md` usage guide, then commit, push and open a PR

## Verification
- `pytest` passes. Timeline tests cover:
  - no status changes
  - changes before, inside and after the range
  - a ticket created inside the range
  - an open last interval
- `test_aggregate.py` checks `hours_per_ticket_status` with known timestamps:
  - a ticket moving To Do 10:00 → In Progress 14:00 → Done 16:00 gives 4.0 / 2.0 h
  - time is summed when a ticket goes back into a status
  - time is clipped at the range edges
  - each ticket's row adds up to its total time inside the range
- The client tests cover every HTTP error code mapping to its JA-code.
- `pip install -e .` and then `jira-activity --help` shows the documented usage.
- Manual check against your real Jira Cloud site: `jira-activity report --from <last month start> --to <last month end>`. Compare a couple of tickets' histories against their History tab in the Jira UI.
- `report --verbose` prints `GET /rest/api/3/... -> 200` lines to stderr, with no token, query string or response body. Without the flag, nothing is logged unless there is a warning.
- Error checks: a wrong token gives JA-101, a wrong site gives JA-103 or JA-106, and `--from` after `--to` gives JA-201.
