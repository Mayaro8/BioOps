#!/bin/bash

# Argo Submit Bash Script
# This script takes a submit function name and executes the corresponding argo submit command
# Usage: ./argo_submit.sh <submit_function_name> [--namespace <namespace>] [--wait] [--stop-on-error]

set -euo pipefail

# Default values
NAMESPACE="${NAMESPACE:-default}"
WAIT="${WAIT:-true}"
STOP_ON_ERROR="${STOP_ON_ERROR:-false}"
DRY_RUN="${DRY_RUN:-false}"

# Get submit function name from first argument
SUBMIT_FUNCTION="${1:-}"

if [ -z "$SUBMIT_FUNCTION" ]; then
    echo "Error: Submit function name is required" >&2
    echo "Usage: $0 <submit_function_name> [options]" >&2
    echo "Available functions:" >&2
    grep "def submit_" "$(dirname "$0")/argo.py" | sed 's/.*def //;s/(.*//' | sed 's/^/  - /' >&2
    exit 1
fi

# Parse additional arguments
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --wait)
            WAIT="true"
            shift
            ;;
        --no-wait)
            WAIT="false"
            shift
            ;;
        --stop-on-error)
            STOP_ON_ERROR="true"
            shift
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Helper function to build argo command
build_argo_command() {
    local workflow_template="$1"
    shift
    local command=("argo" "submit" "--from" "$workflow_template" "-n" "$NAMESPACE")
    
    # Add all -p parameters and handle --labels flag
    while [[ $# -gt 0 ]]; do
        if [ "$1" = "--labels" ]; then
            shift
            if [ $# -gt 0 ]; then
                command+=("--labels" "$1")
                shift
            fi
        else
            command+=("-p" "$1")
            shift
        fi
    done
    
    # Add --wait if needed
    if [ "$WAIT" = "true" ]; then
        command+=("--wait")
    fi
    
    # Build a properly quoted command string that can be safely eval'd
    # This handles JSON and other special characters in parameters
    local cmd_str=""
    for arg in "${command[@]}"; do
        # Use printf %q to properly escape special characters
        cmd_str="${cmd_str}$(printf ' %q' "$arg")"
    done
    # Remove leading space and return
    echo "${cmd_str# }"
}

# Helper function to join array with commas
join_with_commas() {
    local IFS=','
    echo "$*"
}

# Helper function to convert JSON array (handles both Python and bash formats)
json_dump_sample_ids() {
    if [ -z "$1" ] || [ "$1" = "[]" ]; then
        echo "[]"
    else
        # If it's already JSON, use as is, otherwise try to convert
        echo "$1"
    fi
}

# Main case statement - matches submit function name and builds appropriate command
case "$SUBMIT_FUNCTION" in
    submit_cutadapt_s3_mounted_multiple_tubes_delay)
        # Required parameters
        : "${INPUT_MODE:?INPUT_MODE is required}"
        : "${RUN_ID:?RUN_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${OUTPUT_DIR:?OUTPUT_DIR is required}"
        : "${INPUT_DIR:?INPUT_DIR is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/cutadapt-s3-mounted-multiple-tubes-delay" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "INPUT_MODE=$INPUT_MODE" \
            "RUN_ID=$RUN_ID" \
            "INPUT_DIR=$INPUT_DIR" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "RAM=$RAM" \
            "CPUS=$CPUS" \
            "--labels" "run_id=$RUN_ID")
        ;;
    
    submit_cutadapt_mgi_multi_tube)
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${INPUT_PATHS_LIST:?INPUT_PATHS_LIST is required}"
        : "${RUNS_LIST:?RUNS_LIST is required}"
        : "${OUTPUT_DIR:?OUTPUT_DIR is required}"
        : "${MGI_CSV_PATH:?MGI_CSV_PATH is required}"
        : "${LANE:?LANE is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/cutadapt-mgi-multi-tube-prod" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "BATCH_ID=$BATCH_ID" \
            "INPUT_PATHS_LIST=$INPUT_PATHS_LIST" \
            "RUNS_LIST=$RUNS_LIST" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "MGI_CSV_PATH=$MGI_CSV_PATH" \
            "LANE=$LANE" \
            "TEL_CHAT=$TEL_CHAT" \
            "TEL_TOKEN=$TEL_TOKEN" \
            "RAM=$RAM" \
            "CPUS=$CPUS" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_fq2bam_s3_mounted_multiple_tubes_delay)
        : "${RUN_ID:?RUN_ID is required}"
        : "${BATCH_ID_OUT:?BATCH_ID_OUT is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        
        # Optional parameters with defaults
        OUTPUT_DIR="${OUTPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        INPUT_DIR="${INPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        ASSEMBLY="${ASSEMBLY:-hg19}"
        MARKDUP="${MARKDUP:-no}"
        BWA_VERSION="${BWA_VERSION:-1}"
        BAM_SUFFIX_MARKDUP="${BAM_SUFFIX_MARKDUP:-markdup}"
        PAIR_END="${PAIR_END:-yes}"
        SPLIT_PER_CHR="${SPLIT_PER_CHR:-no}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/fq2bam-s3-mounted-multiple-tubes-delay" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "RUN_ID=$RUN_ID" \
            "INPUT_DIR=$INPUT_DIR" \
            "BATCH_ID_OUT=$BATCH_ID_OUT" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "RAM=$RAM" \
            "CPUS=$CPUS" \
            "ASSEMBLY=$ASSEMBLY" \
            "MARKDUP=$MARKDUP" \
            "bwa_version=$BWA_VERSION" \
            "BAM_SUFFIX_MARKDUP=$BAM_SUFFIX_MARKDUP" \
            "PAIR_END=$PAIR_END" \
            "Split_per_chr=$SPLIT_PER_CHR" \
            "--labels" "batch_id=$BATCH_ID_OUT")
        ;;
    
    submit_fq2bam_mgi_multiple_tubes_delay)
        : "${RUN_ID:?RUN_ID is required}"
        : "${BATCH_ID_OUT:?BATCH_ID_OUT is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        
        OUTPUT_DIR="${OUTPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        INPUT_DIR="${INPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        ASSEMBLY="${ASSEMBLY:-hg19}"
        MARKDUP="${MARKDUP:-no}"
        BWA_VERSION="${BWA_VERSION:-1}"
        BAM_SUFFIX_MARKDUP="${BAM_SUFFIX_MARKDUP:-markdup}"
        PAIR_END="${PAIR_END:-yes}"
        SPLIT_PER_CHR="${SPLIT_PER_CHR:-no}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/fq2bam-s3-mounted-mgi-multiple-tubes-delay" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "RUN_ID=$RUN_ID" \
            "INPUT_DIR=$INPUT_DIR" \
            "BATCH_ID_OUT=$BATCH_ID_OUT" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "RAM=$RAM" \
            "CPUS=$CPUS" \
            "ASSEMBLY=$ASSEMBLY" \
            "MARKDUP=$MARKDUP" \
            "bwa_version=$BWA_VERSION" \
            "BAM_SUFFIX_MARKDUP=$BAM_SUFFIX_MARKDUP" \
            "PAIR_END=$PAIR_END" \
            "Split_per_chr=$SPLIT_PER_CHR" \
            "--labels" "batch_id=$BATCH_ID_OUT")
        ;;
    
    submit_qc_fq2bam_multiple_tubes_mounted)
        : "${MODE:?MODE is required (all/qc_only/haplo_only)}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${BASENAME:?BASENAME is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${INPUT_DIR:?INPUT_DIR is required}"
        : "${INCLUDE_UNMAPPED:?INCLUDE_UNMAPPED is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        : "${BUILD:?BUILD is required}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/qc-fq2bam-multiple-tubes-mounted" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "INPUT_DIR=$INPUT_DIR" \
            "BATCH_ID=$BATCH_ID" \
            "INCLUDE_UNMAPPED=$INCLUDE_UNMAPPED" \
            "MODE=$MODE" \
            "BASENAME=$BASENAME" \
            "BUILD=$BUILD" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_batchqc)
        : "${MODE:?MODE is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${BASENAME:?BASENAME is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${CONTROL_BATCH_IDS:?CONTROL_BATCH_IDS is required}"
        : "${EXCEL_FILEPATH:?EXCEL_FILEPATH is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM:?RAM is required}"
        : "${JOBS:?JOBS is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        
        INPUT_DIR="${INPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        OUTPUT_DIR="${OUTPUT_DIR:-/mnt/pipeline-v3.0/sth}"
        ASSEMBLY="${ASSEMBLY:-hg19}"
        ENDPOINT="${ENDPOINT:-https://storage.yandexcloud.net}"
        CONTAMINATION_THRESH="${CONTAMINATION_THRESH:-0.1}"
        
        # Convert sample_ids list to comma-separated string
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            # If it's JSON-like, extract sample_id values
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/batch-qc-new-k8" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "BATCH_ID=$BATCH_ID" \
            "TYPE=$MODE" \
            "BASENAME=$BASENAME" \
            "CONTROL_BATCH_IDS=$CONTROL_BATCH_IDS" \
            "EXCEL_FILEPATH=$EXCEL_FILEPATH" \
            "INPUT_DIR=$INPUT_DIR" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "RAM=$RAM" \
            "CPUS=$CPUS" \
            "JOBS=$JOBS" \
            "ASSEMBLY=$ASSEMBLY" \
            "TEL_CHAT=$TEL_CHAT" \
            "TEL_TOEKN=$TEL_TOKEN" \
            "ENDPOINT=$ENDPOINT" \
            "Contamination_thresh=$CONTAMINATION_THRESH" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_gender_comparison_mongo_bitrix)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${BITRIX_TASK_ID:?BITRIX_TASK_ID is required}"
        : "${ALL_SAMPLES:?ALL_SAMPLES is required}"
        : "${EXCLUDE_SAMPLES:?EXCLUDE_SAMPLES is required}"
        : "${ENV:?ENV is required}"
        : "${CONTAMINATION_THRESHOLD:?CONTAMINATION_THRESHOLD is required}"
        : "${CHIP_TYPE:?CHIP_TYPE is required}"
        : "${S3_BUCKET_DIR:?S3_BUCKET_DIR is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        : "${ENDPOINT:?ENDPOINT is required}"
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/gender-comp-assign-prod" \
            "batchid=$BATCH_ID" \
            "bitrix_task_id=$BITRIX_TASK_ID" \
            "all_samples=$ALL_SAMPLES" \
            "exclude_samples=$EXCLUDE_SAMPLES" \
            "ENV=$ENV" \
            "contamination_threshold=$CONTAMINATION_THRESHOLD" \
            "chip_type=$CHIP_TYPE" \
            "s3_bucket_dir=$S3_BUCKET_DIR" \
            "telegram_chat_id=$TEL_CHAT" \
            "telegram_token=$TEL_TOKEN" \
            "endpoint=$ENDPOINT" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_split_bam_multiple_tubes_s3_mounted)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${INPUT_DIR:?INPUT_DIR is required}"
        : "${OUTPUT_DIR:?OUTPUT_DIR is required}"
        : "${REF:?REF is required}"
        : "${MODE:?MODE is required}"
        : "${BASENAME_MARKDUP:?BASENAME_MARKDUP is required}"
        : "${ASSEMBLY:?ASSEMBLY is required}"
        : "${JOBS:?JOBS is required}"
        : "${CPUS:?CPUS is required}"
        : "${RAM_MULTIPLIER:?RAM_MULTIPLIER is required}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/split-bam-multiple-tubes-s3-mounted" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "INPUT_DIR=$INPUT_DIR" \
            "S3_OUT_BUCKET=$OUTPUT_DIR" \
            "BATCH_ID=$BATCH_ID" \
            "REF=$REF" \
            "MODE=$MODE" \
            "BASENAME=$BASENAME_MARKDUP" \
            "ASSEMBLY=$ASSEMBLY" \
            "JOBS=$JOBS" \
            "CPUS=$CPUS" \
            "RAM_Multiplier=$RAM_MULTIPLIER" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_impute_multiple_chromosomes_glimpse)
        : "${REF:?REF is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${BASENAME:?BASENAME is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${JOBS:?JOBS is required}"
        : "${CPUS:?CPUS is required}"
        : "${INPUT_DIR:?INPUT_DIR is required}"
        : "${OUTPUT_DIR:?OUTPUT_DIR is required}"
        : "${BUILD:?BUILD is required}"
        
        GLIMPSE_THREADS="${GLIMPSE_THREADS:-redundant}"
        REF_BIN_PREFIX="${REF_BIN_PREFIX:-Ultra_hrc_hg19}"
        CHUNK_PREFIX="${CHUNK_PREFIX:-Ultra_hrc_hg19_chunks}"
        NEED_AGGREGATION="${NEED_AGGREGATION:-no}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/impute-multiple-chromosomes-glimpse" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "BATCH_ID=$BATCH_ID" \
            "REF=$REF" \
            "BUILD=$BUILD" \
            "BASENAME=$BASENAME" \
            "JOBS=$JOBS" \
            "CPUS=$CPUS" \
            "INPUT_DIR=$INPUT_DIR" \
            "OUTPUT_DIR=$OUTPUT_DIR" \
            "glimpse_threads=$GLIMPSE_THREADS" \
            "ref_bin_prefix=$REF_BIN_PREFIX" \
            "chunk_prefix=$CHUNK_PREFIX" \
            "need_aggregation=$NEED_AGGREGATION" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_haplotypecaller_gvcf2vcf_full_multiple_tubes)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${INPUT_DIR_S3:?INPUT_DIR_S3 is required}"
        : "${OUTPUT_DIR_S3:?OUTPUT_DIR_S3 is required}"
        : "${PLOIDY_DIR_S3:?PLOIDY_DIR_S3 is required}"
        : "${BASENAME_CALLED_VCF:?BASENAME_CALLED_VCF is required}"
        : "${ASSEMBLY:?ASSEMBLY is required}"
        : "${DBSNP_VCF:?DBSNP_VCF is required}"
        : "${DBSNP:?DBSNP is required}"
        : "${REF:?REF is required}"
        : "${REGIONS_WITHOUT_HOMOPOLYMERS:?REGIONS_WITHOUT_HOMOPOLYMERS is required}"
        
        RECALIBRATED="${RECALIBRATED:-no}"
        CPUS_HAPLOTYPECALLER="${CPUS_HAPLOTYPECALLER:-5}"
        RAM="${RAM:-20}"
        CPUS_GVCF2VCF="${CPUS_GVCF2VCF:-10}"
        CHROMOSOMES_IN_PARALLEL="${CHROMOSOMES_IN_PARALLEL:-5}"
        BAM_SUFFIX="${BAM_SUFFIX:-markdup}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/haplotypecaller-gvcf2vcf-full-multiple-tubes" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "BATCH_ID=$BATCH_ID" \
            "INPUT_DIR_S3=$INPUT_DIR_S3" \
            "OUTPUT_DIR_S3=$OUTPUT_DIR_S3" \
            "PLOIDY_DIR_S3=$PLOIDY_DIR_S3" \
            "BASENAME_CALLED_VCF=$BASENAME_CALLED_VCF" \
            "ASSEMBLY=$ASSEMBLY" \
            "RECALIBRATED=$RECALIBRATED" \
            "CPUS_haplotypecaller=$CPUS_HAPLOTYPECALLER" \
            "RAM=$RAM" \
            "CPUS_gvcf2vcf=$CPUS_GVCF2VCF" \
            "CHROMOSOMES_IN_PARALLEL=$CHROMOSOMES_IN_PARALLEL" \
            "BAM_SUFFIX=$BAM_SUFFIX" \
            "DBSNP_VCF=$DBSNP_VCF" \
            "DBSNP=$DBSNP" \
            "REF=$REF" \
            "REGIONS_WITHOUT_HOMOPOLYMERS=$REGIONS_WITHOUT_HOMOPOLYMERS" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_transfer_vcf_s3_dev)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${DEST_ENV:?DEST_ENV is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/transfer-vcf-s3-dev" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "BATCH_ID=$BATCH_ID" \
            "DEST_ENV=$DEST_ENV" \
            "TELEGRAM_BOT_TOKEN=$TEL_TOKEN" \
            "TELEGRAM_CHAT_ID=$TEL_CHAT" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_post_imputation_s3_mounted_multitube_delay)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${INPUT_DIR_CALLED_VCF:?INPUT_DIR_CALLED_VCF is required}"
        : "${OUTPUT_DIR_IMPUTED:?OUTPUT_DIR_IMPUTED is required}"
        : "${SUPP_PATH_S3:?SUPP_PATH_S3 is required}"
        : "${REF:?REF is required}"
        : "${BASENAME_CALLED:?BASENAME_CALLED is required}"
        : "${BASENAME_IMPUTED:?BASENAME_IMPUTED is required}"
        : "${BUILD:?BUILD is required}"
        : "${AGREE_TO_BLACKLIST:?AGREE_TO_BLACKLIST is required}"
        : "${JOBS:?JOBS is required}"
        : "${OUTPUT_BUCKET_DIR:?OUTPUT_BUCKET_DIR is required}"
        : "${OUTPUT_REPORTS:?OUTPUT_REPORTS is required}"
        
        RAF="${RAF:-0.95}"
        GPMAX="${GPMAX:-0.001}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/post-imputation-s3-mounted-multitube-delay" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "BATCH_ID=$BATCH_ID" \
            "REF=$REF" \
            "RAF=$RAF" \
            "GPMAX=$GPMAX" \
            "AGREE_TO_BLIST=$AGREE_TO_BLACKLIST" \
            "BASENAME_IMPUTED_VCFS=$BASENAME_IMPUTED" \
            "BASENAME_CALLED_VCF=$BASENAME_CALLED" \
            "BUILD=$BUILD" \
            "JOBS=$JOBS" \
            "OUTPUT_DIR=$OUTPUT_BUCKET_DIR" \
            "INPUT_DIR_CALLED_S3=$INPUT_DIR_CALLED_VCF" \
            "INPUT_DIR_IMPUTED_S3=$OUTPUT_DIR_IMPUTED" \
            "OUTPUT_REPORTS_MINIO=$OUTPUT_REPORTS" \
            "SUPP_PATH_S3=$SUPP_PATH_S3" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_beagle_imputation)
        : "${DATE_BATCH_ID:?DATE_BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${BUCKET:?BUCKET is required}"
        : "${CHUNK_SIZE:?CHUNK_SIZE is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/beagle-prod" \
            "samples-list=$SAMPLE_IDS_CSV" \
            "batch-id=$DATE_BATCH_ID" \
            "bucket=$BUCKET" \
            "chunk-size=$CHUNK_SIZE" \
            "--labels" "batch_id=$DATE_BATCH_ID")
        ;;
    
    submit_hla)
        : "${LOCAL_INPUT_HLA:?LOCAL_INPUT_HLA is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${BASENAME:?BASENAME is required}"
        : "${INPUT_HLA_S3:?INPUT_HLA_S3 is required}"
        : "${OUTPUT_HLA_S3:?OUTPUT_HLA_S3 is required}"
        : "${MNT_BUCKET_HLA:?MNT_BUCKET_HLA is required}"
        : "${REFERENCE:?REFERENCE is required}"
        : "${ENV:?ENV is required}"
        
        SAMPLE_IDS_JSON=$(json_dump_sample_ids "$SAMPLE_IDS")
        COMMAND=$(build_argo_command \
            "workflowtemplate/hla-multiple-tubes-s3-mounted" \
            "SAMPLE_IDS=$SAMPLE_IDS_JSON" \
            "INPUT_DIR=$LOCAL_INPUT_HLA" \
            "INPUT_DIR_S3=$INPUT_HLA_S3" \
            "OUTPUT_DIR_S3=$OUTPUT_HLA_S3" \
            "BUCKET=$MNT_BUCKET_HLA" \
            "reference=$REFERENCE" \
            "BASENAME=$BASENAME" \
            "ENV=$ENV" \
            "--labels" "INPUT_DIR_S3=$INPUT_HLA_S3")
        ;;
    
    submit_hla_parser)
        : "${MONGO_DB_HLA:?MONGO_DB_HLA is required}"
        : "${JOBS_HLA_PARSER:?JOBS_HLA_PARSER is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/hla-parser-s3" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "Mongo_DB=$MONGO_DB_HLA" \
            "JOBS=$JOBS_HLA_PARSER" \
            "--labels" "Mongo_DB=$MONGO_DB_HLA")
        ;;
    
    submit_lk_files_s3)
        : "${DATE_BATCH_ID:?DATE_BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${CALLED_BASENAME:?CALLED_BASENAME is required}"
        : "${ASSEMBLY:?ASSEMBLY is required}"
        : "${SPLIT_MODE:?SPLIT_MODE is required}"
        
        # Note: SAMPLE_IDS passed directly, not as JSON in this case
        COMMAND=$(build_argo_command \
            "workflowtemplate/lk-file-s3-mounted-multitube-delay" \
            "sample_ids=$SAMPLE_IDS" \
            "date_batch_id=$DATE_BATCH_ID" \
            "batch_id=$BATCH_ID" \
            "called_basename=$CALLED_BASENAME" \
            "ASSEMBLY=$ASSEMBLY" \
            "SPLIT_MODE=$SPLIT_MODE" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_inheritance)
        : "${files_paths:?files_paths is required}"
        : "${reference:?reference is required}"
        : "${clinvar_db:?clinvar_db is required}"
        
        # Note: SAMPLE_IDS passed directly as string/list
        COMMAND=$(build_argo_command \
            "workflowtemplate/inheritance-multiple-tubes-dev" \
            "files_paths=$files_paths" \
            "reference=$reference" \
            "clinvar_db=$clinvar_db" )
        ;;
    
    submit_apoe)
        : "${ENV:?ENV is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/apoe" \
            "tube_ids=$SAMPLE_IDS_CSV" \
            "env=$ENV" \
            "--labels" "env=$ENV")
        ;;
    
    submit_transfer_bam_s3_dev)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${DEST_ENV:?DEST_ENV is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/transfer-bam-s3-dev" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "BATCH_ID=$BATCH_ID" \
            "DEST_ENV=$DEST_ENV" \
            "TELEGRAM_BOT_TOKEN=$TEL_TOKEN" \
            "TELEGRAM_CHAT_ID=$TEL_CHAT" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_analyze_prs_traits_mito)
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        
        # Note: SAMPLE_IDS passed directly as tube_ids
        COMMAND=$(build_argo_command \
            "workflowtemplate/analyze-full-multiple-tubes-mm-meta-plus-prod" \
            "tube_ids=$SAMPLE_IDS")
        ;;
    
    submit_yleaf)
        : "${BATCH_ID:?BATCH_ID is required}"
        : "${ENV:?ENV is required}"
        : "${INPUT_MODE:?INPUT_MODE is required}"
        : "${INPUT_TUBES:?INPUT_TUBES is required}"
        : "${TEL_CHAT:?TEL_CHAT is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/yleaf-batch-processor-dev" \
            "batch_id=$BATCH_ID" \
            "env=$ENV" \
            "input_mode=$INPUT_MODE" \
            "input_tubes=$INPUT_TUBES" \
            "telegram_channel_id=$TEL_CHAT" \
            "telegram_token=$TEL_TOKEN" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    submit_deep_mito_chunks)
        : "${SAMPLE_IDS:?SAMPLE_IDS is required}"
        : "${JOBS_DEEP_MITO:?JOBS_DEEP_MITO is required}"
        : "${CHUNK_SIZE_DEEP_MITO:?CHUNK_SIZE_DEEP_MITO is required}"
        : "${MODE_DEEP_MITO:?MODE_DEEP_MITO is required}"
        : "${BUILD:?BUILD is required}"
        : "${VERSION_DEEP_MITO:?VERSION_DEEP_MITO is required}"
        : "${TREE_DEEP_MITO:?TREE_DEEP_MITO is required}"
        : "${REF_TYPE:?REF_TYPE is required}"
        : "${HP_THRESHOLD_DEEP_MITO:?HP_THRESHOLD_DEEP_MITO is required}"
        : "${DEDUP_DEEP_MITO:?DEDUP_DEEP_MITO is required}"
        : "${HOTSPOT_DEEP_MITO:?HOTSPOT_DEEP_MITO is required}"
        
        # Convert sample_ids to comma-separated
        if [[ "$SAMPLE_IDS" == *"["* ]] || [[ "$SAMPLE_IDS" == *"{"* ]]; then
            SAMPLE_IDS_CSV=$(echo "$SAMPLE_IDS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(','.join([item.get('sample_id', item) if isinstance(item, dict) else item for item in data]))" 2>/dev/null || echo "$SAMPLE_IDS")
        else
            SAMPLE_IDS_CSV="$SAMPLE_IDS"
        fi
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/deep-mito-hp-chuncks-upd" \
            "SAMPLE_IDS=$SAMPLE_IDS_CSV" \
            "bucket=$CHUNK_SIZE_DEEP_MITO" \
            "JOBS=$JOBS_DEEP_MITO" \
            "MODE=$MODE_DEEP_MITO" \
            "BUILD=$BUILD" \
            "version=$VERSION_DEEP_MITO" \
            "tree=$TREE_DEEP_MITO" \
            "REF_type=$REF_TYPE" \
            "hp_threshold=$HP_THRESHOLD_DEEP_MITO" \
            "dedup=$DEDUP_DEEP_MITO" \
            "HOTSPOT=$HOTSPOT_DEEP_MITO" \
            "--labels" "MODE=$MODE_DEEP_MITO")
        ;;
    
    submit_batch_report)
        : "${TEL_CHAT:?TEL_CHAT is required}"
        : "${TEL_TOKEN:?TEL_TOKEN is required}"
        : "${BATCH_ID:?BATCH_ID is required}"
        
        COMMAND=$(build_argo_command \
            "workflowtemplate/batch-report-add-checks-test-dev" \
            "batch_id=$BATCH_ID" \
            "tel_token=$TEL_TOKEN" \
            "tel_chat_id=$TEL_CHAT" \
            "--labels" "batch_id=$BATCH_ID")
        ;;
    
    *)
        echo "Error: Unknown submit function: $SUBMIT_FUNCTION" >&2
        echo "Available functions:" >&2
        grep "def submit_" "$(dirname "$0")/argo.py" 2>/dev/null | sed 's/.*def //;s/(.*//' | sed 's/^/  - /' >&2 || echo "  (Cannot list - argo.py not found)" >&2
        exit 1
        ;;
esac

# Validate that COMMAND was set
if [ -z "${COMMAND:-}" ]; then
    echo "Error: COMMAND was not set. Unknown submit function or error in command building." >&2
    exit 1
fi

# Execute the command or print it in dry-run mode
if [ "$DRY_RUN" = "true" ]; then
    echo "=== DRY RUN - Argo Submit Command ==="
    echo ""
    echo "$COMMAND"
    echo ""
else
    if [ "$STOP_ON_ERROR" = "true" ]; then
        set -e
        eval "$COMMAND"
    else
        set +e
        eval "$COMMAND"
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "Warning: Command exited with code $EXIT_CODE (stop_on_error is false)" >&2
            exit $EXIT_CODE
        fi
    fi
fi

