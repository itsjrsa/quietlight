#!/usr/bin/env bash
# Docker is already required by QuietLight. Pin the scanner, redact all findings.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
scanner='zricethezav/gitleaks@sha256:e1b35e12a8c6fa8901f060459cfb6b2fc4c484d3afbe3b029733a3bbfab07055'
mode="${1:-staged}"
case "$mode" in
  staged) args=(git /repo --pre-commit --staged) ;;
  tree) args=(dir /repo) ;;
  history) args=(git /repo --log-opts=--all) ;;
  *) printf '%s\n' 'Usage: check-secrets.sh {staged|tree|history}' >&2; exit 2 ;;
esac
result=0
output=$(docker run --rm --network none --read-only --cap-drop ALL \
  --user "$(id -u):$(id -g)" \
  --security-opt no-new-privileges \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  -v "$root:/repo:ro" "$scanner" "${args[@]}" \
  --config /repo/.gitleaks.toml --redact --no-banner --ignore-gitleaks-allow 2>&1) || result=$?
printf '%s\n' "$output"
if [[ "$output" == *Skipping* || "$output" == *'permission denied'* ]]; then
  printf '%s\n' 'Incomplete scan: refusing to pass when files were skipped.' >&2
  exit 1
fi
exit "$result"
