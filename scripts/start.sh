#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
NILE_HOST="${NILE_HOST:-127.0.0.1}"
NILE_PORT="${NILE_PORT:-8000}"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -e '.[vision,sar,test]'
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
mkdir -p data
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/alembic upgrade head
if [ "$NILE_HOST" = "0.0.0.0" ]; then
  NILE_LAN_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk 'NF && $1 !~ /^127\./ { print; exit }')"
  echo "Nile Observer LAN: http://${NILE_LAN_IP:-YOUR-LAPTOP-IP}:${NILE_PORT}. Share only on a trusted local network."
else
  echo "Nile Observer: http://${NILE_HOST}:${NILE_PORT}."
fi
echo 'Token: data/access-token, unless APP_API_KEY is set.'
exec .venv/bin/uvicorn app.main:app --host "$NILE_HOST" --port "$NILE_PORT" --ws-max-size 262144
