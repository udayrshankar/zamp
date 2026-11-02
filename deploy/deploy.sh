#!/usr/bin/env bash
# Pulls the latest main and rebuilds the containers. Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f backend/.env ]; then
  echo "backend/.env is missing. Copy it to the server first." >&2
  exit 1
fi

git pull --ff-only
docker compose up -d --build
docker image prune -f
docker builder prune -f --filter until=24h

docker compose ps
