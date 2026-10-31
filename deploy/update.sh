#!/usr/bin/env bash
# Update the running site after you pushed new code to GitHub.   Run on the server:   bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env file found here. Create it first:  cp .env.example .env  and then  nano .env"; exit 1
fi

if [ -d .git ]; then
  echo "==> Getting the latest code from GitHub"
  git pull --ff-only
else
  echo "(This folder is not a git checkout; skipping 'git pull'. Copy your new files here first.)"
fi

echo "==> Rebuilding and restarting (the big layers are cached, so this is quick)"
docker compose up -d --build
docker image prune -f >/dev/null

echo "==> Status"
docker compose ps
echo
echo "Watch the logs with:  docker compose logs -f app      (press Ctrl+C to stop watching)"
