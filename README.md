<p align="center">
  <img src="assets/icon.png" alt="SUGAR" width="180">
</p>

# authprobe

Login brute-forcer for web forms. Fires candidate user/pass pairs at one login
endpoint, async, and reports which ones come back accepted. No captcha solving,
no lockout bypass, no MFA.

## Quick start

```bash
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Then:

```bash
authprobe          # opens the interface
authprobe --help   # every flag
```

## Open the interface

Run `authprobe` with no arguments and the interface opens: the SUGAR banner
plus a short cheat-sheet.

```
███████╗██╗   ██╗ ██████╗  █████╗ ██████╗
██╔════╝██║   ██║██╔════╝ ██╔══██╗██╔══██╗
███████╗██║   ██║██║  ███╗███████║██████╔╝
╚════██║██║   ██║██║   ██║██╔══██║██╔══██╗
███████║╚██████╔╝╚██████╔╝██║  ██║██║  ██║
╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
 login auditor  //  brute-force by Sugar

usage: authprobe <url> --user NAME -w WORDS [options]
       authprobe --list-presets

examples:
  authprobe https://host/login --user admin -w words.txt --success-status 302
  authprobe https://host --preset wp-login -w words.txt
  authprobe https://host/api/login --preset json-api --user admin -w words.txt

run `authprobe --help` for every flag
```

Start a real run and the same banner is followed by a config panel and a live
progress line (a green `HIT` on a match):

```
┌──────────────────────────────────────────┐
│ authprobe                                │
├──────────────────────────────────────────┤
│ target      : https://example.test/login │
│ method      : POST                       │
│ fields      : username / password        │
│ candidates  : 5000  (1 user x 5000 pass) │
│ mode        : MAX POWER (no rate limit)  │
│ concurrency : unlimited                  │
│ detect      : body lacks 'login_error'   │
│ stop        : first hit                  │
└──────────────────────────────────────────┘
```

## How to use

```bash
# plain form, redirect means success
authprobe https://example.test/login --user admin -w words.txt --success-status 302

# a preset fills in the field names and the failure marker
authprobe https://example.test --preset wp-login -w words.txt
authprobe https://example.test --preset joomla-admin --user admin -w words.txt
authprobe https://example.test --preset django-admin --user admin -w words.txt

# json login, a "token" in the response means it worked
authprobe https://example.test/api/login --preset json-api --user admin -w words.txt

# several users, "Invalid credentials" is the failure string
authprobe https://example.test/login --users users.txt -w words.txt --failure-body "Invalid credentials"

# dump a report
authprobe https://example.test/login --user admin -w words.txt --json report.json
```

`authprobe --list-presets` prints the built-ins: `generic-form`, `wp-login`,
`joomla-admin`, `django-admin`, `json-api`.

### Getting the marker right

Detection matters more than speed. A redirect on success is
`--success-status 302`. An error string that only shows on failure is the most
reliable, `--failure-body "..."`. A token or dashboard string on success is
`--success-body "..."`. When unsure, hit the endpoint once with a good and a bad
password and diff the two.

## Install per distro

Needs Python 3.10+ and git. The only dependency is httpx, pure python, so you
rarely need a compiler. Each block installs the toolchain, clones, and sets up
the venv.

### Debian / Ubuntu / Mint / Kali

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### Arch / Manjaro / EndeavourOS

```bash
sudo pacman -Syu --needed git python python-pip python-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### CachyOS

CachyOS is Arch, so pacman is the same. The one difference is the shell:
CachyOS ships **fish**, and the venv's `activate` is a bash script. Fish can't
parse it, so `source .venv/bin/activate` dies:

```
case "$(uname)" in
^~~^
'case' builtin não está dentro de um bloco switch case
```

That leaves your PATH untouched, so the next `pip` is the system pip and you hit
Arch's PEP 668 wall:

```
error: externally-managed-environment
```

Source the **fish** activate instead (or skip activation completely):

```fish
sudo pacman -Syu --needed git python python-pip python-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python -m venv .venv
source .venv/bin/activate.fish     # the plain `activate` will not work here
pip install -e ".[dev]"

authprobe                          # opens the interface
```

Or drive the venv directly. This works in any shell and dodges PEP 668:

```fish
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m authprobe.cli   # opens the interface
```

In bash or zsh, `source .venv/bin/activate` is fine.

### Fedora / RHEL / CentOS Stream

```bash
sudo dnf install -y git python3 python3-pip python3-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### openSUSE

```bash
sudo zypper install -y git python311 python311-pip python311-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

On older openSUSE use `python3` instead of `python311`.

### Alpine Linux

```bash
sudo apk add git python3 py3-pip py3-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Alpine is musl but httpx and friends are pure python, so no build toolchain. If
something ever needs to compile, add `build-base`.

### Termux (Android)

```bash
pkg update && pkg upgrade -y
pkg install -y git python clang libffi openssl rust
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### Alpine inside Termux

```bash
pkg install -y git proot-distro
proot-distro install alpine
proot-distro login alpine
# now inside alpine
apk add git python3 py3-pip py3-virtualenv
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### Arch inside Termux

```bash
pkg install -y git proot-distro
proot-distro install archlinux
proot-distro login archlinux
# now inside arch
pacman -Syu --needed git python python-pip
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

### pipx

```bash
git clone https://github.com/SugarUnded/brute-force-4-me
cd brute-force-4-me
pipx install .
```

## Flags

| Flag | Meaning |
|------|---------|
| `--preset NAME` | detection preset (`--list-presets`) |
| `--user` / `--users` | one username or a file of them |
| `-w, --wordlist` | password list, blank lines and `#` comments skipped |
| `--user-field` / `--pass-field` | form field names |
| `--success-status` | comma-separated codes that mean success |
| `--success-body` | substring that must be present on success |
| `--failure-body` | substring that must be absent on success |
| `--json-body` | send the pair as JSON |
| `-c, --concurrency` | parallel requests, `0` = unlimited (default) |
| `-t, --timeout` | per-request timeout (default 10) |
| `-H K:V`, `-d K:V` | extra headers / form fields |
| `--no-stop` | keep going after a hit |
| `--json FILE` | write results to a file |

Exit code 0 if at least one pair worked, 1 if not.

## Tuning

No rate limiter, and concurrency is unlimited by default: every candidate goes
out at once. The httpx pool is opened to match, so the only real ceiling is your
file-descriptor limit. On a big wordlist that is a lot of sockets, so check
`ulimit -n` first (a stock 1024 will choke).

Cap it with `-c N` when you want to be gentle:

| Target | `-c` |
|--------|------|
| A site you also serve real users on | 16 |
| Staging or a box that's yours | 128 |
| Localhost or a throwaway container | 512 |
| Something with lockout or a WAF | 1 to 4 |

Bump `-t` for slow hosts, lower it on flaky links. `--no-stop` only matters in
capped mode; in unlimited mode everything is already out. Reading the response:
`429`/`503` means you're being throttled, drop `-c`. Rising latency means you're
the flood. The same instant response for every candidate usually means a WAF is
answering and your marker is meaningless, so check with a manual `curl` first.

## Notes on output

The banner, panel and progress go to **stderr**; results and `--json` go to
**stdout**. `-q` turns off progress, `--no-banner` just the banner. On a
non-UTF-8 terminal the logo falls back to a `#` font, and colors only appear on
a TTY. `NO_COLOR=1` kills colors, `FORCE_COLOR=1` forces them,
`AUTHPROBE_ASCII=plain` forces the plain logo.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
