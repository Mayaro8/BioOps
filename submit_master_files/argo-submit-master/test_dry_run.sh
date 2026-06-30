#!/bin/bash

# Example script to test the dry run with sample values

export DATE_BATCH_ID="test_batch_123"
export SAMPLE_IDS='[{"sample_id":"sample1"},{"sample_id":"sample2"}]'
export BUCKET="my-bucket"
export CHUNK_SIZE="100"
export NAMESPACE="default"
export WAIT="true"

echo "Testing dry run with sample values:"
echo "DATE_BATCH_ID=$DATE_BATCH_ID"
echo "SAMPLE_IDS=$SAMPLE_IDS"
echo "BUCKET=$BUCKET"
echo "CHUNK_SIZE=$CHUNK_SIZE"
echo ""
echo "---"

./dry_run_beagle.sh


