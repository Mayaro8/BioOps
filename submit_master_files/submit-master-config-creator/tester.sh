#!/bin/bash

# Help function
show_help() {
    echo "Usage: $0 <stage> <seq_type> <mode> <cluster_num> <mongo_cluster_label>"
    echo ""
    echo "Parameters:"
    echo "  stage               : Deployment stage (1, 2, 3)"
    echo "  seq_type            : Sequencer type (illumina , mgi)"
    echo "  mode                : Operation mode (all, [specifi list of steps])"
    echo "  cluster_num         : Kubernetes cluster (1, 2, 3, 4, 5, 6, 7)"
    echo "  mongo_cluster_label : cluster that runs Mongo-requiring WFs (common, dev)"
    echo ""
    echo "Options:"
    echo "  --help    Show this help message"
}

# Check for help flag
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    show_help
    exit 0
fi

# Check if all required arguments are provided
if [ $# -ne 5 ]; then
    echo "Error: Incorrect number of arguments"
    echo ""
    show_help
    exit 1
fi

# Assign arguments to variables
stage="${1}"
seq_type="${2}"
mode="${3}"
cluster_num="${4}"
mongo_cluster_label="$5"

# Your script logic continues here...
echo "Running with parameters:"
echo "  Stage: $stage"
echo "  Sequence Type: $seq_type"
echo "  Mode: $mode"
echo "  Cluster Number: $cluster_num"
echo "  MongoDB Cluster Label: $mongo_cluster_label"


samples_ids_str=b5h3x5,mf3839,sw1690,bj3151
runid=batch011225
batch_id=batch011225
batch_date_id=2025-12-01
run_num=394
input_paths_list="MGI_25.09.2025_part2/Pool_12.2/E250087581_L01_10199/E250087581_L01,Run12.2_2_runs/E250087577_L01_10315/E250087577_L01,Run12.2_2_runs/E250087616_L01_10318/E250087616_L01,Run12.2_part3/Pool_12.2/E250087589_L01_10345/E250087589_L01,Run12.2_part3/Pool_12.2/E250087629_L01_10342/E250087629_L01"
runs_list=E250087581,E250087577,E250087616,E250087589,E250087629
tel_chat=368160490
tel_token=8460318633:AAErC5oZx7qgp7N-y-uv9LRLQS6cnKA725c

mgi_csv_path=s3://genotek-testing/vdwgs/mgi/Run${run_num}.csv
lane=L01
output_main_dir=data
genotek_input_dir=genotek-testing/data
raw_pipeline_dir=pipeline-v3.0/data/${batch_date_id}
pipeline_dir=pipeline-v3.0/${batch_id}
batch_qc_dir=pipeline-v3.0/batch_QC
imputation_dir=pipeline-v3.0/glimpse_imputation_run${run_num}
post_imp_dir=post_imputation_reports/${batch_id}
assembly=hg19
ref_panel=ultraold
basename_markdup=markdup
basename_called=called.filtered
basename_imputed=imputed

delay=0
step=1
chunk_size=1

mode_cutadapt=s3_transfer
cpus_cutadapt=3
ram_cutadapt=6
bwa_version=1
paired_end=yes
markdup=yes
cpus_fq2bam=6
ram_fq2bam=25
split_per_chr=no
mode_bamqc=all
include_unmapped=no
cpus_bamqc=4
ram_bamqc=24
control_batch_ids=batch010425,batch010525,batch010825,batch010925,batch020425,batch020525,batch020925,batch030425,batch030525,batch030925,batch040425,batch040525,batch040725,batch040925,batch050425,batch050525,batch050925,batch060425,batch060525,batch060625,batch060925,batch070425,batch070525,batch080425,batch100325,batch110325,batch120325,batch130325,batch130525,batch140325,batch140525,batch150325,batch150525,batch160325,batch160525,batch160725,batch170225,batch170325,batch170525,batch170725,batch180225,batch180325,batch180525,batch180725,batch190225,batch190325,batch190525,batch200225,batch200325,batch200525,batch210225,batch210325,batch210525,batch220225,batch220325,batch230225,batch230325,batch230425,batch240225,batch240325,batch240425,batch240625,batch240725,batch250425,batch250625,batch250725,batch260425,batch260625,batch270425,batch270725,batch280425,batch280725,batch290425,batch290725,batch300425,batch300725,batch310725,batch260925,batch091025,batch111025
excel_filepath="s3://genotek-testing/vdwgs/excel/Run${run_num}.xlsx"
endpoint=storage.yandexcloud.net
mode_batch_qc=prod
jobs_batch_qc=30
cpus_batch_qc=2
ram_batch_qc=4
contamination_thresh=0.1

env=prod
all_samples=from_task
exclude_samples=from_task
chip_type="vdWGS1.0"
cpus_sex_assignment=2
ram_sex_assignment=4
jobs_split=25
mode_split=chr
cpus_split=5
ram_multiplier_split=2
jobs_imputation=76
jobs_imp_split=50
cpus_imputation=79
cpus_imp_split=20
imp_split_chunk_size=50
glimpse_threads=nah
ref_bin_prefix=Ultra_hrc_hg19
chunk_prefix_prefix=Ultra_hrc_hg19_chunks
need_aggregation=no
chrs_in_parallel=5
ref_fasta=/mnt/pipeline-v3.0/ref/hg19/hg19.fa
dbsnp_vcf=/mnt/pipeline-v3.0/db/hg19/dbsnp.target_positions.hg19.vcf
dbsnp=/mnt/pipeline-v3.0/db/hg19/dbsnp.target_positions.hg19.vcf.gz
regions_without_homopolymers=/mnt/pipeline-v3.0/db/hg19/regions_without_homopolymer.hg19.bed
recalibrated=no
cpus_haplotypecaller=5
ram_haplotypecaller=25
raf=0.001
gpmax=0.95
supp_path_s3=/mnt/pipeline-v3.0/db/hg19/supporting_post_imp
agree_to_blacklist=n
jobs_post_imp=23


###
beagle_chunk_size=50
local_input_hla=/home/hla
output_hla_s3=/mnt/pipeline-v3.0/hla
mnt_bucket_hla=/mnt/pipeline-v3.0
input_hla_s3=${batch_id}
mongo_db_hla=mass-results
jobs_hla_parser=20
mode_lk=auto
clinvar_db=clinvar_our_criteria_2021-09-01.tsv
chunk_size_deep_mito=100
jobs_deep_mito=10
mode_deep_mito=vdwgs
version_deep_mito=v1
tree_deep_mito=yfull_mtree_1.02.22621_2025-03-06
ref_type=rsrs
hp_threshold_deep_mito=0.1
dedup_deep_mito=y
hotspot_deep_mito=100


#### Paths and Universal Variables
    > variables_s1.tsv
    echo -e "value\tvariable" >> variables_s1.tsv

    echo -e "samples_ids_str\t$samples_ids_str" >> variables_s1.tsv
    echo -e "runid\t$run_id" >> variables_s1.tsv
    echo -e "run_num\t$run_num" >> variables_s1.tsv
    echo -e "batch_id\t$batch_id" >> variables_s1.tsv
    echo -e "batch_date_id\t$batch_date_id" >> variables_s1.tsv
    echo -e "assembly\t$assembly" >> variables_s1.tsv
    echo -e "ref_panel\t$ref_panel" >> variables_s1.tsv
    echo -e "markdup\t$markdup" >> variables_s1.tsv
    echo -e "basename_markdup\t$basename_markdup" >> variables_s1.tsv
    echo -e "basename_called\t$basename_called" >> variables_s1.tsv
    echo -e "basename_imputed\t$basename_imputed" >> variables_s1.tsv
    echo -e "output_storage_folder\t$output_main_dir" >> variables_s1.tsv
    echo -e "tel_chat\t$tel_chat" >> variables_s1.tsv
    echo -e "tel_token\t$tel_token" >> variables_s1.tsv
    echo -e "endpoint\t$endpoint" >> variables_s1.tsv


    echo -e "delay\t$delay" >> variables_s1.tsv
    echo -e "step\t$step" >> variables_s1.tsv
    echo -e "chunk_size\t$chunk_size" >> variables_s1.tsv

    echo -e "input_paths_list\t$input_paths_list" >> variables_s1.tsv
    echo -e "runs_list\t$runs_list" >> variables_s1.tsv
    echo -e "genotek_input_dir\t/mnt/$genotek_input_dir" >> variables_s1.tsv
    echo -e "main_mgi_output_dir\t$raw_pipeline_dir" >> variables_s1.tsv
    echo -e "raw_pipeline_dir\t/mnt/$raw_pipeline_dir" >> variables_s1.tsv
    echo -e "s3_raw_pipeline_dir\ts3://$raw_pipeline_dir" >> variables_s1.tsv
    echo -e "pipeline_dir\t/mnt/$pipeline_dir" >> variables_s1.tsv
    echo -e "pipeline_dir_s3\ts3://$pipeline_dir" >> variables_s1.tsv
    echo -e "batch_qc_dir\t/mnt/$batch_qc_dir" >> variables_s1.tsv
    echo -e "batch_qc_dir_s3\ts3://$batch_qc_dir" >> variables_s1.tsv
    echo -e "imputation_dir\t/mnt/$imputation_dir" >> variables_s1.tsv
    echo -e "post_imp_dir\t$post_imp_dir" >> variables_s1.tsv
    echo -e "output_main_dir\t$output_main_dir" >> variables_s1.tsv

    cp variables_s1.tsv variables_s2.tsv
    cp variables_s1.tsv variables_s3.tsv
    
if [[ $stage == 1 || $stage == "1" ]]; then
    rm variables_s2.tsv variables_s3.tsv
    #### Stage 1 variables:
    echo -e "mgi_csv_path\t$mgi_csv_path" >> variables_s1.tsv
    echo -e "lane\t$lane" >> variables_s1.tsv
    echo -e "mode_cutadapt\t$mode_cutadapt" >> variables_s1.tsv
    echo -e "cpus_cutadapt\t$cpus_cutadapt" >> variables_s1.tsv
    echo -e "ram_cutadapt\t$ram_cutadapt" >> variables_s1.tsv
    echo -e "bwa_version\t$bwa_version" >> variables_s1.tsv
    echo -e "paired_end\t$paired_end" >> variables_s1.tsv
    echo -e "markdup\t$markdup" >> variables_s1.tsv
    echo -e "cpus_fq2bam\t$cpus_fq2bam" >> variables_s1.tsv
    echo -e "ram_fq2bam\t$ram_fq2bam" >> variables_s1.tsv
    echo -e "split_per_chr\t$split_per_chr" >> variables_s1.tsv
    echo -e "mode_bamqc\t$mode_bamqc" >> variables_s1.tsv
    echo -e "include_unmapped\t$include_unmapped" >> variables_s1.tsv
    echo -e "cpus_bamqc\t$cpus_bamqc" >> variables_s1.tsv
    echo -e "ram_bamqc\t$ram_bamqc" >> variables_s1.tsv
    echo -e "control_batch_ids\t$control_batch_ids" >> variables_s1.tsv
    echo -e "excel_filepath\t$excel_filepath" >> variables_s1.tsv
    echo -e "mode_batch_qc\t$mode_batch_qc" >> variables_s1.tsv
    echo -e "jobs_batch_qc\t$jobs_batch_qc" >> variables_s1.tsv
    echo -e "cpus_batch_qc\t$cpus_batch_qc" >> variables_s1.tsv
    echo -e "ram_batch_qc\t$ram_batch_qc" >> variables_s1.tsv
    echo -e "contamination_thresh\t$contamination_thresh" >> variables_s1.tsv
    

elif [[ $stage == 2 || $stage == "2" ]]; then
    rm variables_s1.tsv variables_s3.tsv
    ### Stage 2 Variables:
    echo -e "bitrix_task_id\t$bitrix_task_id" >> variables_s2.tsv
    echo -e "all_samples\t$all_samples" >> variables_s2.tsv
    echo -e "exclude_samples\t$exclude_samples" >> variables_s2.tsv
    echo -e "chip_type\t$chip_type" >> variables_s2.tsv
    echo -e "sex_env\t$env" >> variables_s2.tsv    
    echo -e "contamination_thresh\t$contamination_thresh" >> variables_s2.tsv
    echo -e "cpus_sex_assignment\t$cpus_sex_assignment" >> variables_s2.tsv
    echo -e "ram_sex_assignment\t$ram_sex_assignment" >> variables_s2.tsv
    echo -e "jobs_split\t$jobs_split" >> variables_s2.tsv
    echo -e "mode_split\t$mode_split" >> variables_s2.tsv
    echo -e "cpus_split\t$cpus_split" >> variables_s2.tsv
    echo -e "ram_multiplier_split\t$ram_multiplier_split" >> variables_s2.tsv
    echo -e "jobs_imputation\t$jobs_imputation" >> variables_s2.tsv
    echo -e "cpus_imputation\t$cpus_imputation" >> variables_s2.tsv
    echo -e "glimpse_threads\t$glimpse_threads" >> variables_s2.tsv
    echo -e "jobs_imp_split\t$jobs_imp_split" >> variables_s2.tsv
    echo -e "cpus_imp_split\t$cpus_imp_split" >> variables_s2.tsv
    echo -e "imp_split_chunk_size\t$imp_split_chunk_size" >> variables_s2.tsv
    echo -e "ref_bin_prefix\t$ref_bin_prefix" >> variables_s2.tsv
    echo -e "chunk_prefix_prefix\t$chunk_prefix_prefix" >> variables_s2.tsv
    echo -e "need_aggregation\t$need_aggregation" >> variables_s2.tsv
    echo -e "chrs_in_parallel\t$chrs_in_parallel" >> variables_s2.tsv
    echo -e "dbsnp_vcf\t$dbsnp_vcf" >> variables_s2.tsv
    echo -e "dbsnp\t$dbsnp" >> variables_s2.tsv
    echo -e "regions_without_homopolymers\t$regions_without_homopolymers" >> variables_s2.tsv
    echo -e "recalibrated\t$recalibrated" >> variables_s2.tsv
    echo -e "ref_path\t$ref_fasta" >> variables_s2.tsv
    echo -e "cpus_haplotypecaller\t$cpus_haplotypecaller" >> variables_s2.tsv
    echo -e "ram_haplotypecaller\t$ram_haplotypecaller" >> variables_s2.tsv
    echo -e "raf\t$raf" >> variables_s2.tsv
    echo -e "gpmax\t$gpmax" >> variables_s2.tsv
    echo -e "output_reports_path_s3\t$output_reports_path_s3" >> variables_s2.tsv
    echo -e "supp_path_s3\t$supp_path_s3" >> variables_s2.tsv
    echo -e "agree_to_blacklist\t$agree_to_blacklist" >> variables_s2.tsv
    echo -e "jobs_post_imp\t$jobs_post_imp" >> variables_s2.tsv


elif [[ $stage == 3 || $stage == "3" ]]; then
    rm variables_s1.tsv variables_s2.tsv
    ###Stage 3 Variables     
    echo -e "beagle_chunk_size\t$beagle_chunk_size" >> variables_s3.tsv
    echo -e "local_input_hla\t$local_input_hla" >> variables_s3.tsv
    echo -e "output_hla_s3\t$output_hla_s3" >> variables_s3.tsv
    echo -e "mnt_bucket_hla\t$mnt_bucket_hla" >> variables_s3.tsv
    echo -e "input_hla_s3\t$input_hla_s3" >> variables_s3.tsv
    echo -e "mongo_db_hla\t$mongo_db_hla" >> variables_s3.tsv
    echo -e "jobs_hla_parser\t$jobs_hla_parser" >> variables_s3.tsv
    echo -e "env\t$env" >> variables_s3.tsv    
    echo -e "mode_lk\t$mode_lk" >> variables_s3.tsv
    echo -e "clinvar_db\t$clinvar_db" >> variables_s3.tsv
    echo -e "jobs_deep_mito\t$jobs_deep_mito" >> variables_s3.tsv
    echo -e "mode_deep_mito\t$mode_deep_mito" >> variables_s3.tsv
    echo -e "chunk_size_deep_mito\t$chunk_size_deep_mito" >> variables_s3.tsv
    echo -e "version_deep_mito\t$version_deep_mito" >> variables_s3.tsv
    echo -e "tree_deep_mito\t$tree_deep_mito" >> variables_s3.tsv
    echo -e "ref_type\t$ref_type" >> variables_s3.tsv
    echo -e "hp_threshold_deep_mito\t$hp_threshold_deep_mito"  >> variables_s3.tsv
    echo -e "dedup_deep_mito\t$dedup_deep_mito" >> variables_s3.tsv
    echo -e "hotspot_deep_mito\t$hotspot_deep_mito" >> variables_s3.tsv

fi

#### Execution

if [[ $cluster_num == 1 || $cluster_num == "1"  ]]; then
    cluster=pipeline-v3
elif [[ $cluster_num == 2 || $cluster_num == "2"  ]]; then
    cluster=pipeline-v3-2
elif [[ $cluster_num == 3 || $cluster_num == "3"  ]]; then
    cluster=pipeline-v3-3
elif [[ $cluster_num == 4 || $cluster_num == "4"  ]]; then
    cluster=pipeline-v3-4
elif [[ $cluster_num == 4 || $cluster_num == "5"  ]]; then
    cluster=pipeline-v3-common-2
elif [[ $cluster_num == 4 || $cluster_num == "6"  ]]; then
    cluster=pipeline-v3-common-3
elif [[ $cluster_num == 4 || $cluster_num == "7"  ]]; then
    cluster=pipeline-v3-common-4
else
    echo "add cluster num 1 or 2 or 3 or 4"
    exit 1
fi 

if [[ $mongo_cluster_label == "common"  ]]; then
    mongo_cluster=pipeline-v3-4
elif [[ $mongo_cluster_label == "dev"  ]]; then
    mongo_cluster=analysis-pipeline-dev
else
    echo "add mongo cluster label common or dev. common is Argo 158.160.187 and dev is xx.131.x.18"
    exit 1
fi 



if [[ $stage == 1 || $stage == "1" ]]; then
    python stage1_config-creator.py variables_s1.tsv methods.tsv ${seq_type} ${mode} ${cluster} ${mongo_cluster}
elif [[ $stage == 2 || $stage == "2" ]]; then
    python stage2_config-creator.py variables_s2.tsv methods.tsv illumina ${mode} ${cluster} ${mongo_cluster}
elif [[ $stage == 3 || $stage == "3" ]]; then
    python stage3_config-creator.py variables_s3.tsv methods.tsv illumina ${mode} ${cluster} ${mongo_cluster}
else
    echo -e "There are only three stages.. please choose one of them..(1,2,3)\nExitting..."
    sleep 3
    exit 1
fi


#aws s3 cp ${batch_id}_clus-${cluster}_mongo-${mongo_cluster}_stage${stage}.json s3://pipeline-v3.0/${config_output_dir}/${batch_id}_clus-${cluster_num}_mongo-${mongo_cluster_label}_stage${stage}.json --endpoint-url=https://storage.yandexcloud.net