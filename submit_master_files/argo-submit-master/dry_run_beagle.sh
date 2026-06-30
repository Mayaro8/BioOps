#!/bin/bash

# Dry run script for beagle argo submit command
# This script echoes the command that would be executed without actually running it
# Usage: ./dry_run_beagle.sh

set -euo pipefail
DATE_BATCH_ID=2025-06-26
SAMPLE_IDS=hz9280
BUCKET=data
CHUNK_SIZE=50

# Default values
NAMESPACE="${NAMESPACE:-default}"
WAIT="${WAIT:-true}"

# Required parameters (set these or they'll fail)
DATE_BATCH_ID="${DATE_BATCH_ID:?DATE_BATCH_ID is required}"
SAMPLE_IDS="${SAMPLE_IDS:?SAMPLE_IDS is required}"
BUCKET="${BUCKET:?BUCKET is required}"
CHUNK_SIZE="${CHUNK_SIZE:?CHUNK_SIZE is required}"

# Convert sample_ids to comma-separated (same logic as argo_submit.sh)
if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
    SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
else
    SAMPLE_IDS_CSV="$SAMPLE_IDS"
fi

# Build the command exactly as argo_submit.sh does
command=("argo" "submit" "--from" "workflowtemplate/beagle-prod" "-n" "$NAMESPACE")

# Add all -p parameters
command+=("-p" "samples-list=$SAMPLE_IDS_CSV")
command+=("-p" "batch-id=$DATE_BATCH_ID")
command+=("-p" "bucket=$BUCKET")
command+=("-p" "chunk-size=$CHUNK_SIZE")
command+=("-p" "chip-type=gsa3")
command+=("-p" "chunks-count='{{= asInt(sprig.floor(len(split(workflow.parameters['\''samples-list'\''])) / workflow.parameters['\''chunk-size'\''])) }}'")
command+=("-p" "preimpute-chunks-prefix-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/preimpute/'")
command+=("-p" "preimpute-splitted-chroms-prefix-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/splitted_chroms/'")
command+=("-p" "output-phased-chrom-vcf-dir-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/'")
command+=("-p" "output-imputed-chrom-vcf-dir-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/'")
command+=("-p" "imputed-batch-vcf-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/merged.vcf.gz'")
command+=("-p" "postimpute-chunks-prefix-key='s3://genotek-testing/data/batch/{{ workflow.parameters.batch-id }}/postimpute/'")
command+=("-p" "chromosomes-list='[\"chrX\",\"chr1\",\"chr2\",\"chr3\",\"chr4\",\"chr5\",\"chr6\",\"chr7\",\"chr8\",\"chr9\",\"chr10\",\"chr11\",\"chr12\",\"chr13\",\"chr14\",\"chr15\",\"chr16\",\"chr17\",\"chr18\",\"chr19\",\"chr20\",\"chr21\",\"chr22\"]'")

# Add labels
command+=("--labels" "batch_id=$DATE_BATCH_ID")

# Add --wait if needed
if [ "$WAIT" = "true" ]; then
    command+=("--wait")
fi

# Echo the command (don't execute it)
echo "=== DRY RUN - Argo Submit Command for Beagle ==="
echo ""
echo "${command[@]}"
echo ""

