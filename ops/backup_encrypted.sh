#!/usr/bin/env bash
# Manual encrypted PostgreSQL backup. NOT an automatic backup schedule.
# Requirements: Docker Compose v2, PostgreSQL container running, age installed.
# Backup output directory must be a mounted off-server encrypted destination.
set -euo pipefail
umask 077

: "${HI_AGE_RECIPIENT:?Set public age recipient}"
: "${HI_BACKUP_DIR:?Set absolute offsite/mounted backup destination}"
if ! command -v age >/dev/null 2>&1 || ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: age and Docker Compose v2 are required." >&2
  exit 1
fi
if [[ "${HI_BACKUP_DIR}" != /* || ! -d "${HI_BACKUP_DIR}" ]]; then
  echo "BLOCKED: HI_BACKUP_DIR must be an existing absolute directory." >&2
  exit 1
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
destination_dir="$(cd "${HI_BACKUP_DIR}" && pwd -P)"
if [[ "${destination_dir}" == "${here}" || "${destination_dir}" == "${here}/"* ]]; then
  echo "BLOCKED: backup directory cannot be inside the source repository." >&2
  exit 1
fi
tmpdir="$(mktemp -d "${destination_dir}/.hi-backup-XXXXXXXX")"
trap 'rm -rf -- "$tmpdir"' EXIT

cd "$here"
# stdout goes directly to age; no plaintext pg_dump is written to disk.
docker compose --env-file ops/production.env -f docker-compose.production.yml exec -T db \
  sh -ec 'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner' \
  | age -r "$HI_AGE_RECIPIENT" -o "$tmpdir/backup.age"

if [[ ! -s "$tmpdir/backup.age" ]]; then
  echo "BLOCKED: encrypted backup is empty." >&2
  exit 1
fi
file="${destination_dir}/horario-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}.pgdump.age"
mv -- "$tmpdir/backup.age" "$file"
sha256sum "$file" > "$file.sha256"
chmod 600 "$file" "$file.sha256"
echo "Encrypted backup written; verify off-site replication and perform restoration drill."
echo "Backup path: $file"
