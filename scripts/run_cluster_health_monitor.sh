#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
