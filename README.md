# jira-activity

A command line tool that shows which statuses your Jira Cloud tickets were in during a period, and for how many hours.

For a date range you choose, it shows:

- **Time per status**: total hours and number of tickets per status.
- **Status timeline**: one coloured bar per ticket over the period.
- **Tickets per status**: which tickets were in each status, and for how long.
- **Hours per status**: a ticket × status table of hours, with totals.

A ticket counts as yours if it was assigned to you at some point in the period.

## Requirements

- Python 3.11 or later
- A **Jira Cloud** site (`https://<your-site>.atlassian.net`). Jira Server / Data Center is not supported.
- An Atlassian API token for your account

## Installation

```
pip install .
```

This installs the `jira-activity` command. For development, use a virtual environment:

```
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

## Getting started

1. **Create an API token** at <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. **Save your details (optional):**
   ```
   jira-activity configure --site https://acme.atlassian.net --email me@acme.se
   ```
   You are asked for the token (the input is hidden), and then:
   `Save site, email and token in the OS keychain? [y/N]`.
   Nothing is saved unless you answer `y`.
3. **Run a report:**
   ```
   jira-activity report --from 2026-09-01 --to 2026-09-30
   ```

Run `jira-activity --help` or `jira-activity <command> --help` at any time.

## Commands

### `jira-activity report`

Shows the four sections listed above for the period.

| Option | Required | Description |
|---|---|---|
| `--from YYYY-MM-DD` | yes | First day of the period. |
| `--to YYYY-MM-DD` | yes | Last day of the period. This day is **included**. The period can be at most 366 days. |
| `--site URL` | no | Jira site, for example `https://acme.atlassian.net`. |
| `--email EMAIL` | no | Email address of your Atlassian account. |
| `--token TOKEN` | no | Jira API token. Prefer the environment variable or the keychain, because options end up in shell history. |
| `--project KEY` | no | Only include tickets in this project, for example `WEB`. |
| `--verbose` | no | Log each Jira request (method, path and status code) to stderr. |

Examples:

```
jira-activity report --from 2026-09-01 --to 2026-09-30
jira-activity report --from 2026-09-01 --to 2026-09-07 --project WEB --verbose
```

### `jira-activity configure`

Asks for your API token and saves the site, email and token in the OS keychain (Windows Credential Manager, macOS Keychain, or Secret Service on Linux), but **only if you confirm**.

| Option | Required | Description |
|---|---|---|
| `--site URL` | yes | Jira site, for example `https://acme.atlassian.net`. |
| `--email EMAIL` | yes | Email address of your Atlassian account. |

`configure` does not test the credentials against Jira. A wrong token shows up as `JA-101` on your next `report`.

## Where credentials come from

`report` takes each value (site, email and token) from the first place that has it:

1. Command line option (`--site`, `--email`, `--token`)
2. Environment variable (`JIRA_SITE`, `JIRA_EMAIL`, `JIRA_API_TOKEN`)
3. OS keychain, saved by `configure`
4. A prompt in the terminal. The token is typed in hidden.

If a value is missing and there is no terminal to ask in (for example in a script), the command stops with `JA-302`.

## Reading the report

- **Hours are calendar hours**, not working hours. A ticket left in *In Progress* over a weekend counts 48 hours for that weekend.
- **Days start and end in your computer's timezone.** If the period crosses a daylight-saving change, the hours near that change can be off by one.
- **The timeline is approximate.** Each character covers a slice of the period and is coloured by the status in the middle of that slice. A status shorter than one slice may not show in the bar. The hours tables are always exact.
- A dot (`·`) in the timeline means the ticket did not exist yet.
- Hours are rounded to 0.1. The *Total* row in the hours table adds up the rounded cells, so it can differ by 0.1 from the *Time per status* table.
- Statuses are listed in the order they first appear, which usually follows your workflow.
- You can save the report to a file, for example `jira-activity report ... > report.txt`. Redirected output is always written as UTF-8. Errors and the progress spinner go to stderr, so they never end up in the file.

## Privacy and security

- **Nothing is saved without your confirmation.** `configure` saves only after you answer `y`, and only to the OS keychain. No file is ever written.
- **The token is never printed or logged.** It is not shown in error messages either.
- **Logging is off by default.** With `--verbose`, each request is logged to stderr as method, path and status code only. Query strings, headers and response bodies are never logged.
- The tool only **reads** from Jira. It never changes tickets.
- **Credentials are only sent to Jira Cloud.** The site must be exactly `https://<your-site>.atlassian.net`. Other hosts, a username or password inside the URL, and custom ports are refused (`JA-202`), so a typo or a crafted URL such as `https://acme.atlassian.net@evil.example` cannot send your token elsewhere. Jira Cloud custom domains are therefore not supported.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | An error was shown as `[JA-xxx]` (see below) |
| 2 | Wrong command usage, for example a missing `--from` |
| 130 | Cancelled with Ctrl+C |

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| JA-101 | Jira rejected the credentials (HTTP 401). | Check the email and API token, and create a new token if needed. |
| JA-102 | No permission for this Jira resource (HTTP 403). | Ask a Jira admin for access to the project. |
| JA-103 | Jira resource not found (HTTP 404). | Check the site URL. |
| JA-104 | Rate limit still exceeded after 3 retries (HTTP 429). | Wait a few minutes and try again. |
| JA-105 | Jira server error (HTTP 5xx). | Try again later. |
| JA-106 | Could not connect to the Jira site. | Check the URL and your network connection. |
| JA-107 | The request timed out after 30 seconds. | Try again, or use a shorter period or `--project`. |
| JA-108 | Jira answered in an unexpected format. | Check that the site is a Jira Cloud site. |
| JA-109 | Jira rejected the request (HTTP 400). | Usually an unknown `--project`. Jira's own message is shown. |
| JA-110 | Jira answered with an unexpected HTTP status. | Try again. Use `--verbose` to see the status code. |
| JA-111 | The site's SSL certificate could not be verified. | Check your VPN or company proxy. Proxies that inspect traffic need their certificate trusted by Python. |
| JA-112 | The request could not be completed, for example because of too many redirects. | Check that the site URL points directly to your Jira Cloud site. |
| JA-113 | Jira kept returning more result pages than expected (over 1000 pages, or the same page twice). | Use a shorter period or `--project`, and try again. |
| JA-201 | Invalid date range. | Use `YYYY-MM-DD`, and make sure `--from` is not after `--to`. |
| JA-202 | Invalid Jira site URL. The reason is shown in brackets. | Use the form `https://<your-site>.atlassian.net`, with no username, password or port. |
| JA-203 | Invalid email address. | Use the email address of your Atlassian account. |
| JA-204 | The date range is longer than 366 days. | Split the period into several reports. |
| JA-301 | The OS keychain could not be read or written. | Check that your OS keychain is available and unlocked. |
| JA-302 | No Jira credentials found. | Pass the options, set the environment variables, or run `configure`. |
| JA-303 | A credential was left empty at the prompt. | Run again and type the value, or pass it as an option. |
| JA-304 | The OS keychain backend failed unexpectedly. | Restart your session or keychain service, or use the environment variables instead. |
| JA-305 | Input ended before an answer was given (Ctrl+Z / Ctrl+D). | Run again and answer the prompt. |
| JA-401 | The report could not be written to the output. | The pipe or file closed early. Check the command you piped the output into. |
| JA-999 | Unexpected error. | Please report it, with the error name shown. |

## Known limits

- **One Jira request per ticket** is needed to read its history, so long periods with many tickets take longer. A progress spinner shows how far it has got.
- The Jira search covers **one extra day on each side** of your period, because Jira reads search dates in your Jira profile's timezone. Time outside your period is cut away, so the hours are not affected.
- After 10 statuses, the colours repeat.

## Development

The code is split into layers so that all I/O lives in one place:

```
src/jira_activity/
  cli.py          commands, options, and turning errors into exit codes
  errors.py       one error class per failure, each with a unique JA code
  domain/         pure logic with no I/O: models, timeline, aggregation, report
  adapters/       all I/O: Jira HTTP client, keychain and prompts, terminal output, clock
  utils/logger.py the only logging setup
tests/            unit tests, one file per module
```

Run the tests:

```
python -m pytest
```

The tests never call a real Jira site or touch your real keychain: HTTP calls and the keyring are faked. The domain logic and the rendering run for real.
