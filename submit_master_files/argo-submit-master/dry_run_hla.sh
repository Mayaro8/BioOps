#!/bin/bash

# Dry run script for HLA argo submit command
# This script echoes the command that would be executed without actually running it
# Usage: ./dry_run_hla.sh

set -euo pipefail
LOCAL_INPUT_HLA=/home/hla
SAMPLE_IDS='[{"tubeid":"hz9280","filename":"hz9280.batch260625.markdup.hg19.bam","delay":0}]'
BASENAME=markdup
INPUT_HLA_S3=batch260625
OUTPUT_HLA_S3=/mnt/pipeline-v3.0/hla
MNT_BUCKET_HLA=/mnt/pipeline-v3.0
REFERENCE=hg19
ENV=prod

# Default values
NAMESPACE="${NAMESPACE:-default}"
WAIT="${WAIT:-true}"

# Required parameters (set these or they'll fail)
LOCAL_INPUT_HLA="${LOCAL_INPUT_HLA:?LOCAL_INPUT_HLA is required}"
SAMPLE_IDS="${SAMPLE_IDS:?SAMPLE_IDS is required}"
BASENAME="${BASENAME:?BASENAME is required}"
INPUT_HLA_S3="${INPUT_HLA_S3:?INPUT_HLA_S3 is required}"
OUTPUT_HLA_S3="${OUTPUT_HLA_S3:?OUTPUT_HLA_S3 is required}"
MNT_BUCKET_HLA="${MNT_BUCKET_HLA:?MNT_BUCKET_HLA is required}"
REFERENCE="${REFERENCE:?REFERENCE is required}"
ENV="${ENV:?ENV is required}"

# Helper function to convert JSON array (same as argo_submit.sh)
json_dump_sample_ids() {
    if [ -z "$1" ] || [ "$1" = "[]" ]; then
        echo "[]"
    else
        # If it's already JSON, use as is, otherwise try to convert
        echo "$1"
    fi
}

# Convert sample_ids to JSON format (same logic as argo_submit.sh)
SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")

# Build the command exactly as argo_submit.sh does
command=("argo" "submit" "--from" "workflowtemplate/hla-multiple-tubes-s3-mounted" "-n" "$NAMESPACE")

# Add all -p parameters
command+=("-p" "SAMPLE_IDS=$SAMPLE_IDS_JSON")
command+=("-p" "INPUT_DIR=$LOCAL_INPUT_HLA")
command+=("-p" "INPUT_DIR_S3=$INPUT_HLA_S3")
command+=("-p" "OUTPUT_DIR_S3=$OUTPUT_HLA_S3")
command+=("-p" "BUCKET=$MNT_BUCKET_HLA")
command+=("-p" "reference=$REFERENCE")
command+=("-p" "BASENAME=$BASENAME")
command+=("-p" "ENV=$ENV")

# Add labels
command+=("--labels" "INPUT_DIR_S3=$INPUT_HLA_S3")

# Add --wait if needed
if [ "$WAIT" = "true" ]; then
    command+=("--wait")
fi

# Echo the command (don't execute it)
echo "=== DRY RUN - Argo Submit Command for HLA ==="
echo ""
echo "${command[@]}"
echo ""

