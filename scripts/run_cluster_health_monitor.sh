#!/usr/bin/env bash
set -euo pipefail

cd /home/mayar/bio-ops

echo "=============================="
echo "BioOps cluster health monitor"
echo "Started at: $(date)"

docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor

echo "Finished at: $(date)"
