#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PRODUCTION_DIST_DIR=".next-production"
STANDALONE_ROOT="$PRODUCTION_DIST_DIR/standalone"
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

# Next standalone omits these assets unless they are copied in. The GitHub
# checkout is flat; Replit traces from its workspace root and nests the app.
if [[ -f "$STANDALONE_ROOT/horario-escolar/frontend/server.js" ]]; then
  STANDALONE_APP_DIR="$STANDALONE_ROOT/horario-escolar/frontend"
elif [[ -f "$STANDALONE_ROOT/server.js" ]]; then
  STANDALONE_APP_DIR="$STANDALONE_ROOT"
else
  echo "Next standalone server was not created in $STANDALONE_ROOT." >&2
  exit 1
fi
mkdir -p "$STANDALONE_APP_DIR/$PRODUCTION_DIST_DIR"
cp -R "$PRODUCTION_DIST_DIR/static" "$STANDALONE_APP_DIR/$PRODUCTION_DIST_DIR/static"
if [[ -d public ]]; then
  rm -rf "$STANDALONE_APP_DIR/public"
  cp -R public "$STANDALONE_APP_DIR/public"
fi
