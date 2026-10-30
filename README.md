# authprobe

Async HTTP login endpoint auditor. Sends candidate credential pairs against a
login endpoint and reports which ones are accepted. Built for auditing systems
you own or are authorized in writing to test.

## What it does

- Async, bounded concurrency with an optional requests/sec cap.
- Configurable success detection: status code, a marker that must appear in the
  body, or a failure marker that must disappear.
- **Detection presets** for common logins: generic form, WordPress, Joomla,
  Django admin, JSON API.
- Stops at the first valid credential (or keeps going with `--no-stop`).
- JSON report output.

It does **not** bypass rate limits, CAPTCHAs, MFA, or account lockouts. If the
target defends itself, respect it.

---

## Install

Requires **Python 3.10+**. `authprobe` only depends on `httpx`, which is pure
Python, so no compiler is usually needed.

The recommended path on every distro is a virtualenv:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"     # or: pip install -e .
```

After install the `authprobe` command is on PATH. Without installing, run it as
a module: `python -m authprobe.cli`.

### Debian / Ubuntu / Mint / Kali (apt)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Arch / Manjaro / EndeavourOS (pacman)

```bash
sudo pacman -Syu --needed python python-pip python-virtualenv
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

> Arch's system Python is "externally managed". Do **not** `pip install` globally
> without `--break-system-packages`; use the venv above (or `pipx install .`).

### Fedora / RHEL / CentOS Stream (dnf)

```bash
sudo dnf install -y python3 python3-pip python3-virtualenv
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

### openSUSE (zypper)

```bash
sudo zypper install -y python311 python311-pip python311-virtualenv
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Alpine Linux (apk)

```bash
sudo apk add python3 py3-pip py3-virtualenv git
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

> Alpine uses musl. `httpx` and its deps are pure Python, so no build toolchain
> is needed. If a future dependency compiles, add `build-base`.

### Termux (Android)

`pkg` is Termux's own package manager (apt-based, but separate from a distro).

```bash
pkg update && pkg upgrade -y
pkg install -y python git clang libffi openssl rust
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Alpine inside Termux (proot-distro)

Runs a real Alpine rootfs on Android without touching the host.

```bash
pkg install -y proot-distro git
proot-distro install alpine
proot-distro login alpine
# ---- inside Alpine ----
apk add python3 py3-pip py3-virtualenv git
git clone https://github.com/SugarUnded/brute-force-4-me authprobe
cd authprobe && python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Arch inside Termux (proot-distro, pacman)

```bash
pkg install -y proot-distro git
proot-distro install archlinux
proot-distro login archlinux
# ---- inside Arch ----
pacman -Syu --needed python python-pip git
git clone https://github.com/SugarUnded/brute-force-4-me authprobe
cd authprobe && python -m venv .venv && . .venv/bin/activate
pip install -e .
```

### Isolated install anywhere (pipx)

For a CLI you do not want polluting any environment:

```bash
pipx install .
authprobe --list-presets
```

---

## Usage

```bash
# generic form: redirect (3xx) means success
authprobe https://example.test/login \
  --user admin -w wordlists/passwords.txt --success-status 302

# WordPress: field names + failure marker come from the preset
authprobe https://example.test --preset wp-login -w words.txt

# Joomla admin
authprobe https://example.test --preset joomla-admin --user admin -w words.txt

# Django admin
authprobe https://example.test --preset django-admin --user admin -w words.txt

# JSON API: credentials sent as JSON, a "token" in the body means success
authprobe https://example.test/api/login --preset json-api --user admin -w words.txt

# treat "Invalid credentials" as the failure marker
authprobe https://example.test/login \
  --users users.txt -w words.txt --failure-body "Invalid credentials"

# save a report
authprobe https://example.test/login --user admin -w words.txt --json report.json
```

List the built-in presets:

```bash
authprobe --list-presets
```

### Key flags

| Flag | Meaning |
|------|---------|
| `--preset NAME` | detection preset (see `--list-presets`) |
| `--user` / `--users` | one username, or a file of usernames |
| `-w, --wordlist` | password list (blank lines and `#comments` skipped) |
| `--user-field` / `--pass-field` | form field names (preset defaults, overridable) |
| `--success-status` | comma-separated codes that mean success |
| `--success-body` | substring that must be present on success |
| `--failure-body` | substring that must be absent on success |
| `--json-body` | send credentials as a JSON body |
| `-c, --concurrency` | parallel in-flight requests (default 10) |
| `-r, --rate` | max requests/sec (`0` = unlimited, default) |
| `-t, --timeout` | per-request timeout in seconds (default 10) |
| `-H K:V`, `-d K:V` | extra headers / static form fields |
| `--no-stop` | keep probing after the first hit |
| `--json FILE` | write machine-readable results |

Exit code is `0` when at least one credential is valid, `1` otherwise.

---

## Tuning

Two knobs govern load: `-c` (how many requests are in flight at once) and `-r`
(how many are *started* per second). `-r` is the real safety valve — it spaces
requests out and is honored even when `-c` is high.

**Start low, watch the target, then climb.** A safe ladder:

| Situation | Suggested | Why |
|-----------|-----------|-----|
| Production site you also serve to users | `-c 4 -r 3` | keeps it under your own traffic |
| Staging / dedicated box | `-c 10 -r 20` | fast but not saturating |
| Localhost / throwaway container | `-c 50 -r 0` | no reason to be gentle |
| Target has lockout / WAF | `-c 1 -r 0.5` | one every two seconds |

Rules of thumb:

- **Default `-r 0` is unlimited** — on a real site that is a self-inflicted DoS.
  Always pass `-r` unless you own the box outright.
- Raise `-t` (e.g. `-t 20`) for slow hosts; lower it to fail fast on unreliable
  networks.
- `-c` above ~64 rarely helps a single endpoint; the server becomes the limit.
- Large wordlists: keep `-r` set and use `--no-stop` only when you must find
  *every* valid pair (e.g. checking many users).

### Reading the target's response

- **`429` or `503` showing up** → you are being throttled. Drop `-r`, raise the
  gap, or stop.
- **Connection resets / timeouts spiking** → back off `-c` and `-r`.
- **Latency climbing steadily** → saturating the box, likely your own. Lower both.
- **Same response for every candidate, instantly** → probably a WAF answering
  for the app; your detection markers are useless, re-check with `--verbose`
  style manual `curl` first.

### Detection markers

Getting the success signal right matters more than speed:

- Redirect on success → `--success-status 302` (or use `--preset generic-form`).
- Error string on failure → `--failure-body "Invalid credentials"` (most robust;
  a success page simply won't contain it).
- Token/banner on success → `--success-body '"token"'` or the presence of a
  dashboard string.

When unsure, hit the endpoint once with valid and invalid creds and diff the two
responses before running a wordlist.

---

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests cover detection logic, the rate limiter, hit/no-hit runs, the progress
hook, HTTP-error tolerance, JSON-body mode, the presets, and a concurrency
deadlock regression.

## Legal

Use only against systems you own or have explicit written permission to test.
Unauthorized access to computer systems is illegal in most jurisdictions.
