#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PRODUCTION_DIST_DIR=".next-production"
STANDALONE_APP_DIR="$PRODUCTION_DIST_DIR/standalone/horario-escolar/frontend"
API_PORT="${API_PORT:-8000}"

cd "$FRONTEND_DIR"
BUILD_METADATA_BACKUP="$(mktemp -d)"
cp next-env.d.ts "$BUILD_METADATA_BACKUP/next-env.d.ts"
cp tsconfig.json "$BUILD_METADATA_BACKUP/tsconfig.json"
restore_build_metadata() {
  cp "$BUILD_METADATA_BACKUP/next-env.d.ts" next-env.d.ts
  cp "$BUILD_METADATA_BACKUP/tsconfig.json" tsconfig.json
  rm -rf "$BUILD_METADATA_BACKUP"
}
trap restore_build_metadata EXIT

rm -rf "$PRODUCTION_DIST_DIR"
HI_NEXT_DIST_DIR="$PRODUCTION_DIST_DIR" API_BACKEND_URL="http://127.0.0.1:${API_PORT}" pnpm run build

# Next standalone intentionally omits these assets unless they are copied in.
if [[ ! -f "$STANDALONE_APP_DIR/server.js" ]]; then
  echo "Next standalone server was not created at $STANDALONE_APP_DIR/server.js." >&2
  exit 1
fi
mkdir -p "$STANDALONE_APP_DIR/$PRODUCTION_DIST_DIR"
cp -R "$PRODUCTION_DIST_DIR/static" "$STANDALONE_APP_DIR/$PRODUCTION_DIST_DIR/static"
if [[ -d public ]]; then
  rm -rf "$STANDALONE_APP_DIR/public"
  cp -R public "$STANDALONE_APP_DIR/public"
fi
