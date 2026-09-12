#!/usr/bin/env bash
# Quiesce writers, then back up PostgreSQL, original audio, and instance keys.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir=${1:?Usage: scripts/selfhost_backup.sh /absolute/backup-directory}
[[ "$backup_dir" = /* ]] || { echo 'Use an absolute destination'; exit 1; }
umask 077
mkdir -p "$backup_dir"
[[ ! -e "$backup_dir/database.dump" ]] || { echo 'Backup already exists'; exit 1; }
docker compose stop api worker scheduler
trap 'docker compose start api worker scheduler' EXIT
docker compose exec -T postgres pg_dump -U ollomi -d ollomi -Fc > "$backup_dir/database.dump.part"
mv "$backup_dir/database.dump.part" "$backup_dir/database.dump"
docker compose run --rm --no-deps -T --user 0 --entrypoint tar api -C /data -czf - files > "$backup_dir/audio.tar.gz.part"
mv "$backup_dir/audio.tar.gz.part" "$backup_dir/audio.tar.gz"
cp .env "$backup_dir/instance.env"
git rev-parse HEAD > "$backup_dir/upstream-commit.txt"
(cd "$backup_dir" && sha256sum database.dump audio.tar.gz instance.env upstream-commit.txt > SHA256SUMS)
echo "Backup complete: $backup_dir (includes private instance keys)"
