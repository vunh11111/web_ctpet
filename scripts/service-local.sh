#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
# Values in .env use dotenv syntax, not shell syntax. Python loads them safely.
export CUDA_VISIBLE_DEVICES=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("CUDA_VISIBLE_DEVICES", "1"))')
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
setting() { "$ROOT/.venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get(sys.argv[2],sys.argv[3]))' "$ROOT/.env" "$1" "$2"; }
case "$1" in
  model) exec .venv/bin/uvicorn model_service.app:app --host 127.0.0.1 --port "$(setting MODEL_PORT 8109)" --workers 1 ;;
  backend) exec .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port "$(setting API_PORT 8108)" ;;
  worker) exec .venv/bin/python -m backend.worker ;;
  frontend) port=$(setting WEB_PORT 3108); export PUBLIC_WEB_HOST=$(setting PUBLIC_WEB_HOST ''); cd frontend; exec npm run preview -- --port "$port" ;;
  *) echo 'Unknown service' >&2; exit 1 ;;
esac
