#!/usr/bin/env bash
# Services stay in dedicated tmux sessions. Run from any directory.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
if [[ ! -f .env || ! -x .venv/bin/python ]]; then
  echo 'Prepare .env and the project virtual environment first. See README.md.' >&2
  exit 1
fi
mkdir -p data logs
docker compose up -d db
for attempt in {1..30}; do
  if docker compose exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then break; fi
  sleep 1
done
.venv/bin/alembic upgrade head
for service in model backend worker frontend; do
  session="dienbien_pet_demo_$service"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "$service already running"
  else
    tmux new-session -d -s "$session" "cd '$ROOT' && bash scripts/service-local.sh '$service' >> 'logs/$service.log' 2>&1"
    echo "Started $service"
  fi
done
.venv/bin/python -c 'from dotenv import dotenv_values; s=dotenv_values(".env"); print("Frontend: http://localhost:"+s.get("WEB_PORT","3108")+" | Backend: http://localhost:"+s.get("API_PORT","8108")+" | Model API: http://localhost:"+s.get("MODEL_PORT","8109"))'
