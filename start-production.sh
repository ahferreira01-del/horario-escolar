#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
STANDALONE_ROOT="$ROOT_DIR/frontend/.next-production/standalone"
API_PORT="${API_PORT:-8000}"
export API_PORT

if [[ -f "$STANDALONE_ROOT/horario-escolar/frontend/server.js" ]]; then
  FRONTEND_STANDALONE="$STANDALONE_ROOT/horario-escolar/frontend"
elif [[ -f "$STANDALONE_ROOT/frontend/server.js" ]]; then
  FRONTEND_STANDALONE="$STANDALONE_ROOT/frontend"
elif [[ -f "$STANDALONE_ROOT/server.js" ]]; then
  FRONTEND_STANDALONE="$STANDALONE_ROOT"
else
  echo "Production Next standalone server is missing in $STANDALONE_ROOT; run build-production.sh first." >&2
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

STARTUP_TIMEOUT_SECONDS="${HI_STARTUP_TIMEOUT_SECONDS:-60}"
SHUTDOWN_GRACE_SECONDS="${HI_CHILD_SHUTDOWN_SECONDS:-5}"
api_pid=""
web_pid=""

for value_name in STARTUP_TIMEOUT_SECONDS SHUTDOWN_GRACE_SECONDS; do
  value="${!value_name}"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "$value_name must be a positive integer." >&2
    exit 1
  fi
done

child_is_running() {
  local pid="$1" stat after state
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  [[ -r "/proc/$pid/stat" ]] || return 1
  IFS= read -r stat < "/proc/$pid/stat" || return 1
  after="${stat##*) }"
  state="${after%% *}"
  [[ "$state" != "Z" && "$state" != "X" ]]
}

stop_children() {
  local pid deadline any_running
  set +e
  for pid in "$web_pid" "$api_pid"; do
    if [[ -n "$pid" ]] && child_is_running "$pid"; then
      kill -TERM "$pid" 2>/dev/null
    fi
  done

  deadline=$((SECONDS + SHUTDOWN_GRACE_SECONDS))
  while (( SECONDS < deadline )); do
    any_running=0
    for pid in "$web_pid" "$api_pid"; do
      if [[ -n "$pid" ]] && child_is_running "$pid"; then
        any_running=1
      fi
    done
    [[ "$any_running" == "0" ]] && break
    sleep 0.1
  done

  for pid in "$web_pid" "$api_pid"; do
    if [[ -n "$pid" ]] && child_is_running "$pid"; then
      kill -KILL "$pid" 2>/dev/null
    fi
  done
  for pid in "$web_pid" "$api_pid"; do
    [[ -n "$pid" ]] && wait "$pid" 2>/dev/null
  done
}

cleanup() {
  local exit_status=$?
  trap - EXIT INT TERM
  stop_children
  exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

http_ok() {
  python -c 'import sys; from urllib.request import urlopen; response=urlopen(sys.argv[1], timeout=1); sys.exit(0 if 200 <= response.status < 300 else 1)' "$1" >/dev/null 2>&1
}

check_child_during_startup() {
  local label="$1" pid="$2" status
  if ! child_is_running "$pid"; then
    set +e
    wait "$pid"
    status=$?
    set -e
    if [[ "$label" == "API" ]]; then api_pid=""; else web_pid=""; fi
    echo "Production $label stopped before becoming healthy (exit $status)." >&2
    (( status == 0 )) && status=1
    exit "$status"
  fi
}

# Start both services together. GET / is the Autoscale readiness probe and
# stays fail-closed until API dependencies pass /api/ready; /api/health remains
# the API liveness endpoint.
(
  cd "$BACKEND_DIR"
  exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
) &
api_pid=$!
echo "Production API process started (pid=$api_pid)."

(
  cd "$FRONTEND_STANDALONE"
  export HOSTNAME="${HI_BIND_HOST:-0.0.0.0}"
  export PORT="${PORT:?PORT must be provided by the production service.}"
  export API_BACKEND_URL="http://127.0.0.1:${API_PORT}"
  export HI_NEXT_DIST_DIR=".next-production"
  exec node server.js
) &
web_pid=$!
echo "Production frontend process started (pid=$web_pid)."

startup_deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
while true; do
  check_child_during_startup "API" "$api_pid"
  check_child_during_startup "frontend" "$web_pid"

  api_live=false
  api_ready=false
  web_live=false
  proxied_api_live=false
  proxied_api_ready=false
  http_ok "http://127.0.0.1:${API_PORT}/api/health" && api_live=true
  if [[ "$api_live" == true ]]; then
    http_ok "http://127.0.0.1:${API_PORT}/api/ready" && api_ready=true
  fi
  if [[ "$api_ready" == true ]]; then
    http_ok "http://127.0.0.1:${PORT}/" && web_live=true
  fi
  if [[ "$web_live" == true ]]; then
    http_ok "http://127.0.0.1:${PORT}/api/health" && proxied_api_live=true
    http_ok "http://127.0.0.1:${PORT}/api/ready" && proxied_api_ready=true
  fi

  if [[ "$api_live" == true && "$api_ready" == true && "$web_live" == true \
    && "$proxied_api_live" == true && "$proxied_api_ready" == true ]]; then
    echo "Production web and API became ready; API liveness/readiness checks passed."
    break
  fi
  if (( SECONDS >= startup_deadline )); then
    echo "Production web/API liveness checks did not pass within ${STARTUP_TIMEOUT_SECONDS} seconds." >&2
    exit 1
  fi
  sleep 0.2
done

exited_pid=""
set +e
wait -n -p exited_pid "$api_pid" "$web_pid"
exit_status=$?
set -e

if [[ "$exited_pid" == "$api_pid" ]]; then
  service_name="API"
elif [[ "$exited_pid" == "$web_pid" ]]; then
  service_name="frontend"
else
  service_name="critical process"
fi
echo "Production $service_name exited unexpectedly (exit $exit_status); stopping the other service." >&2
(( exit_status == 0 )) && exit_status=1
exit "$exit_status"
