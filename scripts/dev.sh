#!/usr/bin/env bash
# 네이티브(도커 없이) 실행 스크립트.
#   scripts/dev.sh up      임시 PostgreSQL + API + demo-service + 웹을 백그라운드로 실행
#   scripts/dev.sh down    모두 중지 (--purge 를 붙이면 임시 데이터(.devdata)까지 삭제)
#   scripts/dev.sh status  실행 상태
# 필요: Python 3.11+, Node 20+, PostgreSQL 서버 바이너리(initdb/pg_ctl). 데이터는 .devdata/ (gitignore) 에만 쓴다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/.devdata"
PGDATA="$DATA/pg"
PGRUN="$DATA/pg-run"
LOGS="$DATA/logs"
PIDS="$DATA/pids"
PGPORT="${PGPORT:-55432}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
DEMO_PORT="${DEMO_PORT:-8081}"
WEB_MODE="${WEB_MODE:-prod}"   # prod = next build 후 standalone 서버, dev = next dev

find_pg_bin() {
  if command -v initdb >/dev/null 2>&1; then dirname "$(command -v initdb)"; return; fi
  for d in /usr/lib/postgresql/*/bin /opt/homebrew/opt/postgresql@*/bin /usr/local/opt/postgresql@*/bin; do
    [ -x "$d/initdb" ] && { echo "$d"; return; }
  done
  echo "PostgreSQL 서버 바이너리(initdb)를 찾을 수 없습니다" >&2; exit 1
}

# PostgreSQL 은 root 로 실행할 수 없다. root 면 postgres 계정으로 내려서 실행한다.
as_pg() {
  if [ "$(id -u)" = "0" ]; then runuser -u postgres -- "$@"; else "$@"; fi
}

wait_http() { # url name
  for _ in $(seq 1 90); do
    if curl -fsS -o /dev/null "$1" 2>/dev/null; then return 0; fi
    sleep 1
  done
  echo "$2 가(이) 시간 안에 뜨지 않았습니다: $1 (로그: $LOGS)" >&2; return 1
}

export DATABASE_URL="postgresql+psycopg://aiact:aiact@127.0.0.1:$PGPORT/aiact"
export DEMO_SERVICE_URL="http://127.0.0.1:$DEMO_PORT"
export EVIDENCE_DIR="$DATA/evidence"
export CORS_ORIGINS="http://localhost:$WEB_PORT"
export API_URL="http://127.0.0.1:$API_PORT"

up() {
  local PGBIN; PGBIN="$(find_pg_bin)"
  mkdir -p "$DATA" "$LOGS" "$PIDS" "$PGRUN" "$EVIDENCE_DIR"
  if [ "$(id -u)" = "0" ]; then
    mkdir -p "$PGDATA"; chown -R postgres "$PGDATA" "$PGRUN"; chmod 755 "$DATA"
  fi
  if [ ! -f "$PGDATA/PG_VERSION" ]; then
    as_pg "$PGBIN/initdb" -D "$PGDATA" -U postgres --auth=trust -E UTF8 --locale=C >"$LOGS/initdb.log" 2>&1
  fi
  if ! as_pg "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
    as_pg "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" -w \
      -o "-p $PGPORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=$PGRUN" start >"$LOGS/pg_ctl.log" 2>&1
  fi
  local PSQL=(psql -h 127.0.0.1 -p "$PGPORT" -U postgres -v ON_ERROR_STOP=1 -qAt)
  "${PSQL[@]}" -c "SELECT 1 FROM pg_roles WHERE rolname='aiact'" | grep -q 1 || "${PSQL[@]}" -c "CREATE ROLE aiact LOGIN PASSWORD 'aiact'"
  "${PSQL[@]}" -c "SELECT 1 FROM pg_database WHERE datname='aiact'" | grep -q 1 || "${PSQL[@]}" -c "CREATE DATABASE aiact OWNER aiact"

  (cd "$ROOT/api" && python3 -m app.migrate && python3 -m app.seed)

  cd "$ROOT/demo-service"
  nohup python3 -m http.server "$DEMO_PORT" --bind 127.0.0.1 >"$LOGS/demo-service.log" 2>&1 </dev/null &
  echo $! >"$PIDS/demo"
  cd "$ROOT/api"
  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOGS/api.log" 2>&1 </dev/null &
  echo $! >"$PIDS/api"
  wait_http "http://127.0.0.1:$API_PORT/health" "API"
  wait_http "http://127.0.0.1:$DEMO_PORT/" "demo-service"

  cd "$ROOT/web"
  [ -d node_modules ] || npm install --no-audit --no-fund >"$LOGS/npm-install.log" 2>&1
  if [ "$WEB_MODE" = "dev" ]; then
    nohup npx next dev -p "$WEB_PORT" >"$LOGS/web.log" 2>&1 </dev/null &
    echo $! >"$PIDS/web"
  else
    [ -f .next/standalone/server.js ] || npm run build >"$LOGS/web-build.log" 2>&1
    mkdir -p .next/standalone/.next && rm -rf .next/standalone/.next/static && cp -r .next/static .next/standalone/.next/static
    [ -d public ] && { rm -rf .next/standalone/public; cp -r public .next/standalone/public; }
    PORT="$WEB_PORT" HOSTNAME=127.0.0.1 nohup node .next/standalone/server.js >"$LOGS/web.log" 2>&1 </dev/null &
    echo $! >"$PIDS/web"
  fi
  wait_http "http://127.0.0.1:$WEB_PORT/login" "웹"
  echo "실행 완료: 웹 http://localhost:$WEB_PORT · API http://localhost:$API_PORT · demo-service http://localhost:$DEMO_PORT"
  echo "데모 계정: a-company@demo / consultant@demo / ops@demo (비밀번호 demo1234)"
}

down() {
  for name in web api demo; do
    if [ -f "$PIDS/$name" ]; then
      pid="$(cat "$PIDS/$name")"
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -9 "$pid" 2>/dev/null || true
      rm -f "$PIDS/$name"
    fi
  done
  if [ -f "$PGDATA/PG_VERSION" ]; then
    local PGBIN; PGBIN="$(find_pg_bin)"
    as_pg "$PGBIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
  fi
  if [ "${1:-}" = "--purge" ]; then
    chmod -R u+w "$DATA" 2>/dev/null || true
    rm -rf "$DATA"
    echo "중지 및 임시 데이터 삭제 완료"
  else
    echo "중지 완료 (데이터는 $DATA 에 남아 있습니다. 지우려면: scripts/dev.sh down --purge)"
  fi
}

status() {
  for name in web api demo; do
    if [ -f "$PIDS/$name" ] && kill -0 "$(cat "$PIDS/$name")" 2>/dev/null; then echo "$name: 실행 중 (pid $(cat "$PIDS/$name"))"; else echo "$name: 중지"; fi
  done
  if [ -f "$PGDATA/PG_VERSION" ] && as_pg "$(find_pg_bin)/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then echo "postgres: 실행 중 (port $PGPORT)"; else echo "postgres: 중지"; fi
}

case "${1:-}" in
  up) up ;;
  down) down "${2:-}" ;;
  status) status ;;
  *) echo "사용법: scripts/dev.sh up|down [--purge]|status"; exit 2 ;;
esac
