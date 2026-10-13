#!/bin/sh
# Executado somente na inicialização de um volume NOVO do PostgreSQL oficial.
set -eu
: "${RUNTIME_DB_PASSWORD:?Defina RUNTIME_DB_PASSWORD em .env}"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v runtime_password="$RUNTIME_DB_PASSWORD" <<'PSQL'
SELECT format('CREATE ROLE horario_runtime WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'horario_runtime') \gexec
PSQL
