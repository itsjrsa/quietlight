# Contributing

Keep QuietLight small, readable, and calm. Prefer a clear function over a new
abstraction, an original source over a confident summary, and an honest empty
state over invented content. Open an issue before a substantial feature change.

## Local checks

Install the commit guards before making changes (Python's `pipx` or `uv` can keep
the tool isolated):

```bash
uv tool install pre-commit==4.3.0
pre-commit install
```

Every commit checks the **exact staged snapshot** for private IPs, personal paths,
literal credentials, forbidden runtime files, and unreviewed binaries. It also
runs a pinned Gitleaks container and tests the privacy guard. Docker must be
running; missing tools or failed scans block the commit. Localhost/listen addresses
are the only IP exceptions. Do not add real example IPs to documentation.

Before staging, run `python3 scripts/check_privacy.py --worktree`. After staging,
run `pre-commit run --all-files`. CI repeats the checks and scans Git history.
Hooks can be bypassed locally, so repository branch protection must also require
the **Checks / test** workflow. Do not use hook bypasses to publish private data.

Use Python 3.12+, Node 22+, and Google Chrome. Docker is only needed to run the full
agent stack and the secret-scanning hook. Automated tests use temporary data and never call a model.

```bash
python3 -m unittest discover -s research -p 'test_*.py' -v
python3 -m unittest discover -s journal -p 'test_*.py' -v
cd journal
npm ci --ignore-scripts
npm run build
npm run format:check
npm audit
npm run test:ui
```

The UI test starts its own fixture server on a random localhost port. It covers
desktop, 390px and 320px mobile layouts, settings, logout, empty state, diagrams,
and untrusted Markdown. Set `CHROME_PATH` if Chrome is not at
`/usr/bin/google-chrome`. Browser sandboxing stays enabled. Screenshots are
temporary test artifacts, ignored by Git.

For Python formatting and linting, use `ruff==0.14.1`:

```bash
ruff check .
ruff format --check .
```

Use `ruff format .` and `npm run format` to format changes. Review
[the architecture](docs/architecture.md) before changing the worker or archive.

## Pull requests

Keep changes focused. Include a short explanation and tests; include desktop and
mobile screenshots for visual changes, using synthetic content only. Never attach
your real profile or credentials. Do not change the pinned Hermes version and the
application behavior in one unexplained update.

Contributions are under the project's MIT license. Third-party code and assets
must retain their own required notices.
