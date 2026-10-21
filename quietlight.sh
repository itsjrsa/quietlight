#!/usr/bin/env bash
set -euo pipefail
kit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export HERMES_UID="$(id -u)"
export HERMES_GID="$(id -g)"
compose=(docker compose --project-directory "$kit_dir" -f "$kit_dir/compose.yml")

prepare() {
  umask 077
  mkdir -p "$kit_dir/data/research"
  [[ -f "$kit_dir/data/config.yaml" ]] || cp "$kit_dir/config.example.yaml" "$kit_dir/data/config.yaml"
  [[ -f "$kit_dir/data/research/profile.json" ]] || cp "$kit_dir/research/profile.example.json" "$kit_dir/data/research/profile.json"
}

cli() {
  if [[ -n "$("${compose[@]}" ps --status running -q hermes)" ]]; then
    "${compose[@]}" exec hermes hermes "$@"
  else
    "${compose[@]}" run --rm --no-deps hermes "$@"
  fi
}

case "${1:-help}" in
  prepare) prepare; "${compose[@]}" config --quiet ;;
  pull) "${compose[@]}" pull ;;
  login) prepare; cli auth add openai-codex --type oauth --no-browser ;;
  model) prepare; cli model ;;
  setup) prepare; cli setup ;;
  tools) prepare; cli tools ;;
  start) prepare; "${compose[@]}" up -d --build ;;
  stop) "${compose[@]}" stop ;;
  logs) "${compose[@]}" logs --tail 100 -f ;;
  status) cli cron status ;;
  personalize)
    cli chat --query-file /opt/research-kit/personalize.txt
    ;;
  configure)
    [[ $# == 2 && -f "$2" ]] || { printf '%s\n' 'Usage: ./quietlight.sh configure SETTINGS.json' >&2; exit 2; }
    "${compose[@]}" exec -T hermes python /opt/research-kit/preferences.py configure - < "$2"
    ;;
  preferences|generate|schedule)
    action="$1"; shift
    [[ "$action" != preferences ]] || action=show
    "${compose[@]}" exec -T hermes python /opt/research-kit/preferences.py "$action" "$@"
    ;;
  cli) shift; prepare; cli "$@" ;;
  stage-briefing)
    prepare
    # Refuse duplicates; edit an existing job via the CLI instead.
    python3 - "$kit_dir/data/cron/jobs.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.exists():
    data = json.loads(p.read_text())
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    if any(j.get("name") == "morning-research" for j in jobs):
        sys.exit("morning-research already exists; use cli cron edit morning-research")
PY
    cli cron create '0 8 * * *' "$(<"$kit_dir/research/briefing.txt")" \
      --name morning-research --workdir /opt/data/research --deliver local \
      --paused --paused-reason 'Awaiting topic configuration, model login, and first-run validation'
    ;;
  *)
    printf '%s\n' 'Usage: ./quietlight.sh {prepare|pull|login|model|setup|tools|personalize|configure FILE|preferences|generate|schedule HH:MM|schedule off|stage-briefing|start|stop|status|logs|cli ...}'
    ;;
esac
