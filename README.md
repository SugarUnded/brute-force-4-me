# authprobe

Async HTTP login endpoint auditor. Sends candidate credential pairs against a
single login endpoint and reports which ones are accepted. Built for auditing
systems you own or are authorized in writing to test.

## What it does

- Async, bounded concurrency with an optional requests/sec cap.
- Configurable success detection: status code, a marker that must appear in the
  body, or a failure marker that must disappear.
- Stops at the first valid credential (or keeps going with `--no-stop`).
- JSON report output.

It does **not** bypass rate limits, CAPTCHAs, MFA, or account lockouts. If the
target defends itself, respect it.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# classic: fixed user, password wordlist, redirect means success
authprobe https://example.test/login \
  --user admin \
  -w wordlists/passwords.txt \
  --success-status 302

# multiple users, treat "Invalid credentials" as the failure marker
authprobe https://example.test/login \
  --users wordlists/users.txt \
  -w wordlists/passwords.txt \
  --failure-body "Invalid credentials" \
  -c 5 -r 10

# write a report
authprobe https://example.test/login --user admin -w pw.txt --json report.json
```

### Key flags

| Flag | Meaning |
|------|---------|
| `--user` / `--users` | one username, or a file of usernames |
| `-w, --wordlist` | password list (blank lines and `#comments` skipped) |
| `--success-status` | comma-separated codes that mean success |
| `--success-body` | substring that must be present on success |
| `--failure-body` | substring that must be absent on success |
| `-c, --concurrency` | parallel in-flight requests |
| `-r, --rate` | max requests/sec (`0` = unlimited) |
| `-H K:V`, `-d K:V` | extra headers / static form fields |
| `--no-stop` | keep probing after the first hit |
| `--json FILE` | write machine-readable results |

Exit code is `0` when at least one credential is valid, `1` otherwise.

## Tests

```bash
pytest
```

## Legal

Use only against systems you own or have explicit written permission to test.
Unauthorized access to computer systems is illegal in most jurisdictions.
