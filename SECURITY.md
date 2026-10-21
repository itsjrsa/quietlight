# Security

QuietLight is for **one user on a trusted private network**, not public hosting.
The current main branch is the only maintained version until releases are tagged.

## Report privately

Please use [GitHub's private vulnerability reporting](https://github.com/itsjrsa/quietlight/security/advisories/new)
when enabled. If unavailable, ask the maintainer for a private channel without
posting exploit details, credentials, logs, or private research in a public issue.
There is no promised response SLA.

## What is protected—and what is not

- The default port binds to localhost. Reading requires no login.
- HTTP Host headers must match explicitly allowed hosts, including localhost by
  default. This reduces DNS-rebinding exposure; it does not authenticate readers.
  Configure private addresses and DNS names as described in [running QuietLight](docs/running.md).
- Settings and generation require a random access key. Sessions expire after 24
  hours and are revoked on logout or journal restart. Failed logins are rate-limited.
- The web container runs without root, Linux capabilities, a writable root
  filesystem, the Docker socket, or the provider credential directory.
- The upstream Hermes init starts as root, then drops the agent to the configured
  host UID/GID. The agent can read its own credentials and the shared settings key.
- Markdown and diagrams are untrusted input. Rendering uses sanitization and a
  content security policy. Prompt instructions are **not** a security sandbox.
- The research container has outbound network access, including potential access
  to LAN services. No egress allowlist or hardened multi-tenant isolation is claimed.
- Research briefs and relevant context go to the configured hosted model. Search
  queries and source URLs go to search/extraction providers. Local archival does
  not imply local-only processing; each provider's data-handling policies apply.
- HTTP cookies are not Secure because the private deployment uses HTTP. Use
  encrypted private transport; do not put this service directly on the internet.

## Before sharing code or diagnostics

Never commit `data/`, `.env`, auth files, cookies, settings keys, SQLite databases,
reports, logs, backups, or screenshots of personal settings. Ignore rules are a
guardrail, not a substitute for reviewing the exact files being committed.

Review staged changes and run a secret scanner before every release. If a secret
ever reaches Git, revoke it immediately; deleting the latest file is not enough.
Dependency checks and automated tests reduce risk but do not prove an agent or a
generated briefing is safe or correct.

Install the [pre-commit guards](CONTRIBUTING.md) locally. CI scans source and Git
history with a pinned Gitleaks image, plus project-specific privacy rules. Scanner
findings are redacted; unreadable files fail the scan. The custom guard rejects
non-local IPv4/IPv6 literals, personal machine paths, common credential literals,
private runtime files, and unreviewed binary files. It tests staged blobs rather
than trusting unstaged working files.

Before accepting contributions, enable GitHub secret scanning/push protection and
private vulnerability reporting where available, and require the Checks workflow
on the main branch. These are repository settings, not enabled by configuration
files alone. No pattern scanner can reliably identify every personal name, email,
private hostname, encoded secret, or sensitive fact in prose; human review remains
required, especially for documentation and images.
