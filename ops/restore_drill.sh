#!/usr/bin/env bash
# Restore validation in a SEPARATE DR/STAGING HOST with its own PostgreSQL volume.
# Never modifies the active horario DB. Create and drop only horario_restore_drill.
set -euo pipefail
umask 077
: "${HI_RESTORE_DRILL_CONFIRM:?Set HI_RESTORE_DRILL_CONFIRM=ISOLATED_HOST_ONLY after reviewing the target host}"
: "${HI_AGE_IDENTITY_FILE:?Set path to private age identity outside the repository}"
: "${HI_BACKUP_FILE:?Set path to encrypted .pgdump.age backup}"
if [[ "$HI_RESTORE_DRILL_CONFIRM" != "ISOLATED_HOST_ONLY" ]]; then
  echo "BLOCKED: confirmation requires an isolated recovery host." >&2
  exit 1
fi
if ! command -v age >/dev/null 2>&1 || ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: age and Docker Compose v2 required." >&2
  exit 1
fi
if [[ ! -r "$HI_AGE_IDENTITY_FILE" || ! -r "$HI_BACKUP_FILE" ]]; then
  echo "BLOCKED: recovery key or backup missing." >&2
  exit 1
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
# Fixed non-production database name: it MUST NOT exist before this drill.
dbname=horario_restore_drill
compose=(docker compose --env-file ops/production.env -f docker-compose.production.yml)
exists="$("${compose[@]}" exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -U "$POSTGRES_USER" -d postgres -Atc "SELECT count(*) FROM pg_database WHERE datname = '\''horario_restore_drill'\''"
')"
if [[ "$exists" != "0" ]]; then
  echo "BLOCKED: drill database already exists, refusing to overwrite." >&2
  exit 1
fi
"${compose[@]}" exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE horario_restore_drill"
' >/dev/null

# Streaming decryption to pg_restore: plaintext never written to a host file.
age -d -i "$HI_AGE_IDENTITY_FILE" "$HI_BACKUP_FILE" | \
 "${compose[@]}" exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  exec pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d horario_restore_drill
 '

verdict="$("${compose[@]}" exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -U "$POSTGRES_USER" -d horario_restore_drill -Atc "
  SELECT CASE WHEN
    (SELECT version_num FROM alembic_version LIMIT 1) = '\''0003'\''
    AND (SELECT count(*) FROM pg_class
          WHERE relname IN ('\''memberships'\'','\''grade_proposals'\'','\''published_grades'\'')
            AND relrowsecurity AND relforcerowsecurity)=3
  THEN '\''RESTORE_DRILL_SCHEMA_PASS'\'' ELSE '\''RESTORE_DRILL_SCHEMA_FAIL'\'' END;"
')"
if [[ "$verdict" != "RESTORE_DRILL_SCHEMA_PASS" ]]; then
  echo "RESTORE_DRILL_FAIL: investigate recovered schema before deleting scratch DB." >&2
  exit 1
fi

"${compose[@]}" exec -T db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE horario_restore_drill WITH (FORCE)"
' >/dev/null
echo "RESTORE_DRILL_SCHEMA_PASS: archive decrypted, restored, schema and FORCE RLS checked on isolated host."
echo "This alone is not a full app/RPO/RTO certification; verify runtime isolation and critical user journeys."
