#!/usr/bin/env bash
# Quiesce writers, then back up PostgreSQL, original audio, and instance keys.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir=${1:?Usage: scripts/selfhost_backup.sh /absolute/backup-directory}
[[ "$backup_dir" = /* ]] || { echo 'Use an absolute destination'; exit 1; }
umask 077
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
[[ ! -e "$backup_dir/database.dump" ]] || { echo 'Backup already exists'; exit 1; }
if [[ "${COMPOSE_FILE:-}" == *"deploy/examples/external-api/"* ]] && [[ -f deploy/examples/external-api/.env ]]; then
  instance_env=deploy/examples/external-api/.env
elif [[ -f .env ]]; then
  instance_env=.env
else
  echo 'Cannot find the instance .env; run from its directory or set COMPOSE_FILE to a configured deployment.'
  exit 1
fi
if docker compose config --services | grep -Fxq ollomi-api; then
  api_service=ollomi-api
else
  api_service=api
fi
docker compose stop "$api_service" worker scheduler
trap 'docker compose start "$api_service" worker scheduler' EXIT
docker compose exec -T postgres pg_dump -U ollomi -d ollomi -Fc > "$backup_dir/database.dump.part"
mv "$backup_dir/database.dump.part" "$backup_dir/database.dump"
docker compose run --rm --no-deps -T --user 0 --entrypoint tar "$api_service" -C /data -czf - files > "$backup_dir/audio.tar.gz.part"
mv "$backup_dir/audio.tar.gz.part" "$backup_dir/audio.tar.gz"
cp "$instance_env" "$backup_dir/instance.env"
if git rev-parse --verify HEAD > "$backup_dir/upstream-commit.txt" 2>/dev/null; then
  :
else
  printf '%s\n' 'Published-image deployment; see instance.env for image owner and tag.' > "$backup_dir/upstream-commit.txt"
fi
(cd "$backup_dir" && sha256sum database.dump audio.tar.gz instance.env upstream-commit.txt > SHA256SUMS)
echo "Backup complete: $backup_dir (includes private instance keys)"
