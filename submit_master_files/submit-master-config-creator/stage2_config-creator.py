from codecs import raw_unicode_escape_decode
import json
from typing import Sequence
import pandas as pd
import argparse
import csv
parser = argparse.ArgumentParser(description="Argument inputs for bioinformatics stage")

# Add positional arguments (order matters)
parser.add_argument("variables_file", help="a txt with all variable values, ordered using the same order in this script")
parser.add_argument("methods_file", help="a txt with all method values")
parser.add_argument("seq_type", help="sequencing type: illumina or mgi")
parser.add_argument("steps_order", help="a list of steps wanted to be included")
parser.add_argument("cluster_name", help="cluster_name")
parser.add_argument("mongo_cluster_name", help="cluster compatible with mongo")

args = parser.parse_args()

def csv_to_key_value_dict(filename):
    result = {}
    with open(filename, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 2:
                result[row[0]] = row[1]
    return result

# Usage
var_file =  args.variables_file
var_list = csv_to_key_value_dict(f'{var_file}')

methods_file = args.methods_file
method_names = csv_to_key_value_dict(f'{methods_file}')

sequencer = args.seq_type

steps_list = args.steps_order
steps = steps_list.split(",")
if steps[0] == "all":
    steps = ["sex_bitrix","split","imputation","haplotypecaller","transfer_vcf","post_imp"]

print(steps)
cluster = args.cluster_name
if cluster in ["pipeline-v3-4","pipeline-v3-common-2","pipeline-v3-common-3","pipeline-v3-common-4"]:
    print("Common cluster is chosen: imputation will run as imputation_partition, rest of the step will run on prod clusters of same order as chosen common")

mongo_cluster = args.mongo_cluster_name

sample_ids_str = var_list["samples_ids_str"]
sample_ids_json = [{"sample_id": s.strip()} for s in sample_ids_str.split(",")]

namespace = "default"
run_id = var_list["runid"]
run_number = var_list["run_num"]
batch_id = var_list["batch_id"]
batch_date_id = var_list["batch_date_id"]
assembly = var_list["assembly"]
ref_panel = var_list["ref_panel"]
markdup = var_list["markdup"]
basename_markdup = var_list["basename_markdup"]
basename_called = var_list["basename_called"]
basename_imputed = var_list["basename_imputed"]
tel_chat = var_list["tel_chat"]
tel_token = var_list["tel_token"]
endpoint = var_list["endpoint"]
delay = int(var_list["delay"])
step = int(var_list["step"])
chunk_size = int(var_list["chunk_size"])

# paths
genotek_input_dir = var_list["genotek_input_dir"]
s3_raw_pipeline_dir = var_list["s3_raw_pipeline_dir"]
raw_pipeline_dir = var_list["raw_pipeline_dir"]
pipeline_dir = var_list["pipeline_dir"]
pipeline_dir_s3 = var_list["pipeline_dir_s3"]
batch_qc_dir = var_list["batch_qc_dir"]
batch_qc_dir_s3 = var_list["batch_qc_dir_s3"]
imputation_dir = var_list["imputation_dir"]
post_imp_dir = var_list["post_imp_dir"]

#sex assignment
bitrix_task_id = var_list["bitrix_task_id"]
all_samples_list_dir = var_list["all_samples"]
s3_download_exclude = var_list["exclude_samples"]
chip_type = var_list["chip_type"]
cpus_sex_assignment = var_list["cpus_sex_assignment"]
ram_sex_assignment = var_list["ram_sex_assignment"]
contamination_thresh=var_list["contamination_thresh"]
sex_env=var_list["sex_env"]

# split
jobs_split = var_list["jobs_split"]
mode_split = var_list["mode_split"]
cpus_split = var_list["cpus_split"]
ram_multiplier_split = var_list["ram_multiplier_split"]
# imputation
jobs_imputation = var_list["jobs_imputation"]
cpus_imputation = var_list["cpus_imputation"]
glimpse_threads =var_list["glimpse_threads"]
jobs_imp_split=var_list["jobs_imp_split"]
cpus_imp_split=var_list["cpus_imp_split"]
imp_split_chunk_size=var_list["imp_split_chunk_size"]

ref_bin_prefix =var_list["ref_bin_prefix"]
chunk_prefix_prefix =  var_list["chunk_prefix_prefix"]
need_aggregation = var_list["need_aggregation"]
#HC/GVCF
chrs_in_parallel = var_list["chrs_in_parallel"]
dbsnp_vcf = var_list["dbsnp_vcf"]
dbsnp = var_list["dbsnp"]
regions_without_homopolymers = var_list["regions_without_homopolymers"]
recalibrated = var_list["recalibrated"]
cpus_haplotypecaller = var_list["cpus_haplotypecaller"]
ram_haplotypecaller = var_list["ram_haplotypecaller"]
ref_path = var_list["ref_path"]
#post-imp
raf = var_list["raf"]
gpmax = var_list["gpmax"]
output_reports_path_s3 = var_list["output_reports_path_s3"]
supp_path_s3 = var_list["supp_path_s3"]
agree_to_blacklist = var_list["agree_to_blacklist"]
jobs_post_imp = var_list["jobs_post_imp"]
imputation_dir_batch=imputation_dir+"/"+batch_id
output_main_dir=var_list["output_main_dir"]
#########################

def submit_methods(pipeline_step,cluster,mongo_cluster):
    if pipeline_step == "sex_bitrix":
        config_step = {
        "submit_method": method_names["sex_bitrix"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "batch_id":batch_id,
        "bitrix_task_id" : bitrix_task_id,
        "all_samples": all_samples_list_dir,
        "exclude_samples": s3_download_exclude,
        "contamination_threshold":contamination_thresh,
        "chip_type": chip_type,
        "env": sex_env,
        "s3_bucket_dir": batch_qc_dir_s3,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "tel_chat": tel_chat,
        "tel_token": tel_token,
        "endpoint": endpoint,
        "wait": "true",
        "only_good": "true"        
    }

    if pipeline_step == "split":
        config_step = {
        "submit_method": method_names["split"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "batch_id": batch_id,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir": pipeline_dir,
        "output_dir": pipeline_dir_s3,
        "assembly": assembly,
        "basename_markdup": basename_markdup,
        "jobs": jobs_split,
        "mode": mode_split,
        "ref": ref_panel,
        "ram_multiplier": ram_multiplier_split,
        "cpus": cpus_split,
        "wait": "true",
    }
    if pipeline_step == "imputation":
        config_step = {
        "submit_method": method_names["imputation"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "build": assembly,
        "batch_id": batch_id,
        "ref": ref_panel,
        "basename": basename_markdup,
        "jobs": jobs_imputation,
        "cpus": cpus_imputation,
        "glimpse_threads": glimpse_threads,
        "ref_bin_prefix": ref_bin_prefix,
        "chunk_prefix": chunk_prefix_prefix,
        "need_aggregation": need_aggregation,
        "input_dir": pipeline_dir,
        "output_dir": imputation_dir,
        "wait": "true",
    }
    if pipeline_step == "imputation_partition":
        config_step = {
        "submit_method": method_names["imputation_partition"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "build": assembly,
        "batch_id": batch_id,
        "ref": ref_panel,
        "basename": basename_markdup,
        "jobs_imp_split":jobs_imp_split,
        "cpus_imp_split":cpus_imp_split,
        "imp_split_chunk_size":imp_split_chunk_size,        
        "jobs": jobs_imputation,
        "cpus": cpus_imputation,
        "glimpse_threads": glimpse_threads,
        "ref_bin_prefix": ref_bin_prefix,
        "chunk_prefix": chunk_prefix_prefix,
        "need_aggregation": need_aggregation,
        "input_dir": pipeline_dir,
        "output_dir": imputation_dir,
        "wait": "true",
    }
    if pipeline_step == "haplotypecaller":
        config_step = {
        "submit_method": method_names["haplotypecaller"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "batch_id": batch_id,
        "sample_ids": sample_ids_json,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir_s3": pipeline_dir,
        "output_dir_s3": pipeline_dir,
        "ploidy_dir_s3": batch_qc_dir,
        "basename_called_vcf": basename_called,
        "assembly": assembly,
        "recalibrated": recalibrated,
        "cpus_haplotypecaller": cpus_haplotypecaller,
        "ram": ram_haplotypecaller,
        "chromosomes_in_parallel": chrs_in_parallel,
        "dbsnp_vcf": dbsnp_vcf,
        "dbsnp": dbsnp,
        "regions_without_homopolymers": regions_without_homopolymers,
        "bam_suffix": basename_markdup,
        "ref": ref_path,
        "wait": "true"
    }
    if pipeline_step == "transfer_vcf":
        config_step = {
        "submit_method": method_names["transfer_vcf"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "batch_id": batch_id,
        "sample_ids": sample_ids_json,
        "dest_env":output_main_dir,
        "tel_token": tel_token,
        "tel_chat": tel_chat,
        "wait": "true",
    }
    if pipeline_step == "post_imp":
        config_step = {
        "submit_method": method_names["post_imp"],
        "k8s_cluster_name": cluster,
        "batch_id": batch_id,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "build": assembly,
        "agree_to_blacklist": agree_to_blacklist,
        "jobs": jobs_post_imp,
        "basename_imputed": basename_imputed,
        "basename_called": basename_called,
        "raf": raf,
        "gpmax": gpmax,
        "ref": ref_panel,
        "output_bucket_dir": output_main_dir,
        "input_dir_called_vcf": pipeline_dir,
        "output_dir_imputed": imputation_dir_batch,
        "output_reports": post_imp_dir,
        "supp_path_s3": supp_path_s3,
        "wait": "true",
    }
    return config_step



final_json = []

for s in steps:
    if cluster in ["pipeline-v3-4","pipeline-v3-common-2","pipeline-v3-common-3","pipeline-v3-common-4"] and s == "imputation":
        final_json.append(submit_methods("imputation_partition",cluster,mongo_cluster))
    else:
        final_json.append(submit_methods(s,cluster,mongo_cluster))

with open(f"{batch_id}_clus-{cluster}_mongo-{mongo_cluster}_stage2.json", 'w') as f:
    json.dump(final_json, f, indent=1)