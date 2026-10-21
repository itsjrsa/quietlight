# Running QuietLight

## First run

The settings key is created on the journal's first startup, inside its mounted
data directory. Open Settings → Where do I find my key? for a copyable command
that reads the key from the running container. With the default Docker hostname,
this command works from any folder on the Docker host. It prints the key only in
your terminal; the website never retrieves the key itself.

For a standard checkout, the host file is `data/research/journal/admin-token`
relative to the deployment's Compose directory. A separate source checkout does
not change that location: the journal's `/data` volume mount determines where
the key and archive are stored. Redeploying code preserves that mount and data.

Follow the [README](../README.md). `prepare` creates private files under `data/`
without overwriting an existing configuration. `setup` opens upstream Hermes'
setup flow. For individual changes, use `./quietlight.sh model` and
`./quietlight.sh tools`. The `login` shortcut invokes Hermes' Codex OAuth flow;
use `setup` for other providers. Do not copy another application's credential cache.

The example uses `openai-codex` with `openai-native` search and `tavily` extraction.
Check provider eligibility, quotas, and tool credentials in
[Hermes' documentation](https://hermes-agent.nousresearch.com/docs/).
A model login alone does not validate web extraction. Run a manual edition and
check its citations and coverage gaps before enabling the daily schedule.

`start` builds the journal and starts both containers. The Hermes gateway can take
a little while to become ready. The worker creates its cron job automatically;
you do not need to stage one manually. Use `./quietlight.sh schedule HH:MM`,
`./quietlight.sh schedule off` to control the original topic's time and automatic
research. In web Settings, select a topic and choose daily, weekdays, or weekly,
its time, and (for weekly) its day. Adjust its lookback window to cover the interval.
Each topic's schedule is independent:
direct cron schedule changes may be overwritten by the worker.

For terminal-first setup, including an LLM-ready template and an interactive
Hermes command, see [Personalize your journal](personalization.md).

Research starts at the configured time; publication is later, after research and
archival finish. The machine must be awake and Docker running. Hermes may dispatch
a recently missed job within its grace period; older missed runs are not backfilled.

## Access from your phone

By default, the port is `127.0.0.1:8097`. For Tailscale access, put your machine's
actual Tailscale IPv4 address in an ignored `.env` file at the repository root:

```dotenv
JOURNAL_BIND=YOUR_TAILSCALE_IPV4
JOURNAL_PORT=8097
```

Restart with `./quietlight.sh start`, then open `http://YOUR_TAILSCALE_IPV4:8097`
from a device allowed to reach it on your tailnet. Tailscale must be running before
Docker binds that address. Tailnet access controls remain your responsibility.
Compose also adds `JOURNAL_BIND` to the journal's allowed HTTP hosts. If you use a
private DNS name instead of the address, add `JOURNAL_ALLOWED_HOSTS=YOUR_PRIVATE_DNS_NAME`
to `.env` and restart. Multiple names are comma-separated, without schemes, ports,
paths, or wildcards. Only add names you control. Localhost remains allowed.
The server rejects other Host headers before serving pages or API data to reduce
DNS-rebinding exposure. This check does not authenticate readers or replace
private-network access controls. When running `server.py` outside Compose, its
default allowed hosts are `localhost`, `127.0.0.1`, and `::1`; set the same
environment variable explicitly for other hosts.

Do not use `0.0.0.0` unless you deliberately intend to expose the journal to all
host interfaces. Ordinary LAN HTTP is unencrypted; Tailscale encrypts its transport.

Reading is unauthenticated. Do not forward this port to the public internet.
Settings use an HttpOnly, SameSite=Strict cookie over the private HTTP connection;
this is not a public-hosting authentication system.

## Everyday commands

```bash
./quietlight.sh logs
./quietlight.sh status
./quietlight.sh cli cron list --all
./quietlight.sh stop
./quietlight.sh start
```

`data/research/reports/` contains exported Markdown. All revisions remain in
`data/research/coverage.sqlite3`, even when the index shows only the latest one.
Older revisions are retained for recovery, but have no browsing interface or
revision-specific API yet. Inspect a private backup of the database if needed;
do not upload it to an online database viewer.

## Backups and upgrades

### Upgrading from Fieldnotes

The project is now QuietLight. Use `./quietlight.sh` and update existing scripts
and automation to call it. Browser read/unread history is copied to the
new storage key automatically on the same website origin; the old key is retained.

Fresh installs use the Docker Compose project name `quietlight`. Before starting
an existing deployment with the new Compose file, pin its original project name
in that deployment's `.env`, for example `COMPOSE_PROJECT_NAME=fieldnotes` for a
standard older install. If you used a custom project name, retain that exact name.
Do not run a second Compose project against the same data directory. Keep the
existing data mount and network settings. Renaming a source checkout alone does
not rename or move a separate deployment.

GitHub links now use `itsjrsa/quietlight`. Update an existing checkout with
`git remote set-url origin git@github.com:itsjrsa/quietlight.git`.
Close terminals and editor workspaces using the old folder before moving it,
then reopen the renamed directory. Historical Git commits keep their old names.

Stop both services before copying `data/` to a private, encrypted backup. It
contains credentials, access keys, profile information, and potentially private
research. Keep backups out of Git. Restart afterwards. Restore only while stopped,
preserve ownership and permissions, then check the journal and cron status.

The Hermes image is pinned by digest in `compose.yml`; change it deliberately,
after reading upstream release notes. Back up first, run the automated checks,
then validate a manual edition. `./quietlight.sh pull` refreshes configured images;
`start` rebuilds the journal. Do not run two deployments against the same `data/`.

## When something needs attention

- **Research service offline:** inspect container logs. The UI considers a heartbeat
  older than 90 seconds offline. Check model/tool setup and gateway startup.
- **Research finished but no edition:** inspect Hermes cron history. Successful
  model output is not enough; the archive command must have succeeded.
- **A pending request after restart:** the worker consumes it when idle. An inflight
  request interrupted by a restart is cleared with a warning; check the archive
  and execution history before manually retrying.
- **Execution database unreadable:** dispatch is blocked conservatively. Check
  permissions and database health before retrying; do not delete it to bypass the check.
- **Lost access key:** retrieve `data/research/journal/admin-token` locally. To rotate,
  stop both services, move that exact file to a private location outside the repo,
  and restart. Restarting the journal also revokes all existing sessions.

The journal health check only checks its HTTP service, not research quality,
provider availability, or the worker's progress. There are no remote failure alerts yet.
