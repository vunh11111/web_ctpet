#!/usr/bin/env bash
set -euo pipefail
for service in model backend worker frontend; do
  tmux kill-session -t "dienbien_pet_demo_$service" 2>/dev/null || true
done
echo 'Stopped the four local demo processes. PostgreSQL data is retained.'
