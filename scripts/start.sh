#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -e '.[vision,sar,test]'
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
mkdir -p data
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/alembic upgrade head
echo 'Nile Observer: http://127.0.0.1:8000. Token: data/access-token, unless APP_API_KEY is set.'
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 262144
