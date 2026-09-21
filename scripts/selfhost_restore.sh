#!/usr/bin/env bash
# Restore an Ollomi backup only after integrity and instance-key checks.
set -euo pipefail
cd "$(dirname "$0")/.."

backup_dir=${1:-}
confirmation=${2:-}
if [[ -z "$backup_dir" || "$confirmation" != "--confirm-restore" ]]; then
  echo 'Usage: scripts/selfhost_restore.sh /absolute/backup-directory --confirm-restore'
  echo 'This replaces the PostgreSQL database, original audio and derived search indexes of this instance.'
  exit 2
fi
[[ "$backup_dir" = /* ]] || { echo 'Use an absolute backup directory'; exit 2; }
[[ -d "$backup_dir" ]] || { echo 'Backup directory does not exist'; exit 2; }
for required in SHA256SUMS database.dump audio.tar.gz instance.env upstream-commit.txt; do
  [[ -f "$backup_dir/$required" ]] || { echo "Backup is missing $required"; exit 2; }
done
(cd "$backup_dir" && sha256sum -c --status SHA256SUMS) || {
  echo 'Backup integrity verification failed; nothing was restored.'
  exit 1
}

if [[ "${COMPOSE_FILE:-}" == *"deploy/examples/external-api/"* ]] && [[ -f deploy/examples/external-api/.env ]]; then
  instance_env=deploy/examples/external-api/.env
elif [[ -f .env ]]; then
  instance_env=.env
else
  echo 'Cannot find the instance .env; run from its directory or set COMPOSE_FILE to a configured deployment.'
  exit 2
fi

secret_line() {
  local file=$1
  local lines
  lines=$(grep -E '^OLLOMI_SECRET_KEY=' "$file" || true)
  [[ $(printf '%s\n' "$lines" | sed '/^$/d' | wc -l | tr -d ' ') = 1 ]] || return 1
  printf '%s' "$lines"
}

current_secret=$(secret_line "$instance_env") || {
  echo 'The current .env must contain exactly one OLLOMI_SECRET_KEY line.'
  exit 2
}
backup_secret=$(secret_line "$backup_dir/instance.env") || {
  echo 'The backup instance.env does not contain exactly one OLLOMI_SECRET_KEY line.'
  exit 2
}
[[ "$current_secret" = "$backup_secret" ]] || {
  echo 'OLLOMI_SECRET_KEY differs from the backup; refusing to restore encrypted credentials.'
  exit 1
}

# Reject path traversal and unexpected roots before any writer is stopped.
tar -tzf "$backup_dir/audio.tar.gz" | awk '
  $0 == "files" || $0 == "files/" { next }
  /^files\// {
    path = substr($0, 7)
    if (path == "" || path ~ /(^|\/)\.\.?(\/|$)/ || path ~ /(^|\/)\/+/) exit 1
    next
  }
  { exit 1 }
' || {
  echo 'Audio archive contains an unsafe path; nothing was restored.'
  exit 1
}

if docker compose config --services | grep -Fxq ollomi-api; then
  api_service=ollomi-api
else
  api_service=api
fi

echo 'Stopping API, worker and scheduler. PostgreSQL data and audio will now be replaced.'
docker compose stop "$api_service" worker scheduler
restart_writers() {
  docker compose start "$api_service" worker scheduler
}
trap restart_writers EXIT

docker compose up -d --wait --wait-timeout 90 postgres redis typesense
docker compose exec -T postgres pg_restore --clean --if-exists --no-owner -U ollomi -d ollomi < "$backup_dir/database.dump"

# The volume is mounted at /data for this service.  --confirm-restore above is
# intentionally required because this removes only original audio from it.
docker compose run --rm --no-deps -T --user 0 --entrypoint sh "$api_service" -ec \
  'mkdir -p /data/files && find /data/files -mindepth 1 -depth -delete'
docker compose run --rm --no-deps -T --user 0 --entrypoint tar "$api_service" \
  --no-same-owner --no-same-permissions -C /data -xzf - < "$backup_dir/audio.tar.gz"
docker compose run --rm --no-deps -T --user 0 --entrypoint chown "$api_service" -R 10001:10001 /data/files

# Typesense and pgvector are derivable from records.  Queue the rebuild while
# writers are stopped, then let the worker process it after the trap restarts.
for attempt in $(seq 1 30); do
  if docker compose run --rm --no-deps -T --entrypoint python "$api_service" -c \
    'import urllib.request; urllib.request.urlopen("http://typesense:8108/health", timeout=3).read()'; then
    break
  fi
  [[ "$attempt" = 30 ]] && { echo 'Typesense did not become ready; writers will restart without rebuilding search.'; exit 1; }
  sleep 2
done
docker compose run --rm --no-deps -T --entrypoint python "$api_service" -m selfhost.cli rebuild-search-index
echo 'Restore completed. Writers are restarting; wait for queued search indexing before relying on search.'
