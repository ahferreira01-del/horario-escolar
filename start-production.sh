#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_STANDALONE="$ROOT_DIR/frontend/.next-production/standalone/horario-escolar/frontend"
API_PORT="${API_PORT:-8000}"
export API_PORT

if [[ ! -f "$FRONTEND_STANDALONE/server.js" ]]; then
  echo "Production Next standalone server is missing at $FRONTEND_STANDALONE/server.js; run build-production.sh first." >&2
  exit 1
fi
if [[ -z "${SESSION_SECRET:-}" ]]; then
  echo "SESSION_SECRET is required to start the production API." >&2
  exit 1
fi
if [[ -z "${HI_RUNTIME_DATABASE_URL:-}" ]]; then
  echo "HI_RUNTIME_DATABASE_URL is required to start the production API." >&2
  exit 1
fi

export ENVIRONMENT=production
export COOKIE_SECURE=true
if [[ -z "${PUBLIC_APP_URL:-}" ]]; then
  if [[ -z "${REPLIT_DOMAINS:-}" ]]; then
    echo "PUBLIC_APP_URL or REPLIT_DOMAINS is required in production." >&2
    exit 1
  fi
  public_domain="${REPLIT_DOMAINS%%,*}"
  export PUBLIC_APP_URL="https://${public_domain}"
fi

cd "$BACKEND_DIR"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

api_ready=false
for _ in {1..60}; do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid" 2>/dev/null || true
    echo "Production API stopped before becoming healthy." >&2
    exit 1
  fi
  if python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:" + __import__("os").environ.get("API_PORT", "8000") + "/api/health", timeout=1)' 2>/dev/null; then
    api_ready=true
    break
  fi
  sleep 1
done
if [[ "$api_ready" != true ]]; then
  echo "Production API did not become healthy within 60 seconds." >&2
  exit 1
fi

cd "$FRONTEND_STANDALONE"
export HOSTNAME=0.0.0.0
export PORT="${PORT:?PORT must be provided by the production service.}"
export API_BACKEND_URL="http://127.0.0.1:${API_PORT}"
node server.js
