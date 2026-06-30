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
    if sequencer == "illumina":
        steps = ["cutadapt_illumina","fq2bam_illumina","bamqc","batchqc"]
    elif sequencer == "mgi":
        steps = ["cutadapt_mgi","fq2bam_mgi","bamqc","batchqc"]
    elif sequencer == "surf":
        steps = ["cutadapt_surf","fq2bam_illumina","bamqc","batchqc"]
    elif sequencer == "salus":
        steps = ["cutadapt_surf","fq2bam_illumina","bamqc","batchqc"]
    else:
        raise AssertionError("Please Choose a correct sequencer: illumina or mgi or surf")

print(steps)
cluster = args.cluster_name
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
basename_markdup = var_list["basename_markdup"]
basename_called = var_list["basename_called"]
basename_imputed = var_list["basename_imputed"]
tel_chat = var_list["tel_chat"]
tel_token = var_list["tel_token"]

delay = int(var_list["delay"])
step = int(var_list["step"])
chunk_size = int(var_list["chunk_size"])

# paths
input_paths_list = var_list["input_paths_list"]
runs_list = var_list["runs_list"]
genotek_input_dir = var_list["genotek_input_dir"]
main_mgi_output_dir=var_list["main_mgi_output_dir"]
s3_raw_pipeline_dir = var_list["s3_raw_pipeline_dir"]
raw_pipeline_dir = var_list["raw_pipeline_dir"]
pipeline_dir = var_list["pipeline_dir"]
pipeline_dir_s3 = var_list["pipeline_dir_s3"]
batch_qc_dir = var_list["batch_qc_dir"]
batch_qc_dir_s3 = var_list["batch_qc_dir_s3"]
imputation_dir = var_list["imputation_dir"]
post_imp_dir = var_list["post_imp_dir"]

#cutadapt
mode_cutadapt = var_list["mode_cutadapt"]
cpus_cutadapt = var_list["cpus_cutadapt"]
ram_cutadapt = var_list["ram_cutadapt"]
#cutadapt_mgi
mgi_csv_path = var_list["mgi_csv_path"]
lane = var_list["lane"]
#fq2bam
bwa_version = var_list["bwa_version"]
paired_end = var_list["paired_end"]
markdup = var_list["markdup"]
cpus_fq2bam = var_list["cpus_fq2bam"]
ram_fq2bam = var_list["ram_fq2bam"]
split_per_chr = var_list["split_per_chr"]
#bamqc
mode_bamqc = var_list["mode_bamqc"]
cpus_bamqc = var_list["cpus_bamqc"]
ram_bamqc = var_list["ram_bamqc"]
include_unmapped = var_list["include_unmapped"]
#batchQC
control_batch_ids = var_list["control_batch_ids"]
excel_filepath = var_list["excel_filepath"]
endpoint = var_list["endpoint"]
mode_batch_qc = var_list["mode_batch_qc"]
jobs_batch_qc = var_list["jobs_batch_qc"]
cpus_batch_qc = var_list["cpus_batch_qc"]
ram_batch_qc = var_list["ram_batch_qc"]
contamination_thresh=var_list["contamination_thresh"]
#########################

#PRS lowmem
batchids_prs=var_list["batchids_prs"]
mode_prs=var_list["mode_prs"]

def submit_methods(pipeline_step,cluster,mongo_cluster):
    if pipeline_step == "cutadapt_illumina":
        config_step = {
        "submit_method": method_names["cutadapt_illumina"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "input_mode":mode_cutadapt,
        "sample_ids": sample_ids_json,
        "run_id": run_id,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir": genotek_input_dir,
        "output_dir": raw_pipeline_dir,
        "cpus": cpus_cutadapt,
        "ram": ram_cutadapt,
        "wait": "true",
        "only_good": "false"
    }
    if pipeline_step == "cutadapt_mgi":
        config_step = {
        "submit_method": method_names["cutadapt_mgi"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "batch_id": batch_id,
        "delay_config": {
            "delay": delay,
            "step": 300,
            "chunk_size": 100
        },
        "input_paths_list": input_paths_list,
        "runs_list": runs_list,
        "output_dir": raw_pipeline_dir,
        "mgi_csv_path": mgi_csv_path,
        "lane": lane,
        "tel_chat": tel_chat,
        "tel_token": tel_token,        
        "cpus": cpus_cutadapt,
        "ram": ram_cutadapt,
        "wait": "true",
        "only_good": "false"
    }
    if pipeline_step == "cutadapt_surf":
        config_step = {
        "submit_method": method_names["cutadapt_surf"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "batch_id": batch_id,
        "delay_config": {
            "delay": delay,
            "step": 300,
            "chunk_size": 100
        },
        "input_paths_list": input_paths_list,
        "runs_list": runs_list,
        "output_dir": raw_pipeline_dir,
        "mgi_csv_path": mgi_csv_path,
        "lane": lane,
        "tel_chat": tel_chat,
        "tel_token": tel_token,        
        "cpus": cpus_cutadapt,
        "ram": ram_cutadapt,
        "wait": "true",
        "only_good": "false"
    }
    if pipeline_step == "fq2bam_illumina":
        config_step = {
        "submit_method": method_names["fq2bam_illumina"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "run_id": run_id,
        "batch_id_out": batch_id,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir": raw_pipeline_dir,
        "output_dir": pipeline_dir,
        "assembly": assembly,
        "markdup": markdup,
        "cpus": cpus_fq2bam,
        "ram": ram_fq2bam,
        "bwa_version": bwa_version,
        "bam_suffix_markdup": basename_markdup,
        "pair_end": paired_end,
        "split_per_chr": split_per_chr,
        "wait": "true",
        "only_good": "true"
    }
    if pipeline_step == "fq2bam_mgi":
        config_step = {
        "submit_method": method_names["fq2bam_mgi"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "run_id": batch_id,
        "batch_id_out": batch_id,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir": raw_pipeline_dir,
        "output_dir": pipeline_dir,
        "assembly": assembly,
        "markdup": markdup,
        "cpus": cpus_fq2bam,
        "ram": ram_fq2bam,
        "bwa_version": bwa_version,
        "bam_suffix_markdup": basename_markdup,
        "pair_end": paired_end,
        "split_per_chr": split_per_chr,
        "wait": "true",
        "only_good": "true"
    }
    if pipeline_step == "bamqc":
        config_step = {
        "submit_method": method_names["bamqc"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "mode" : mode_bamqc,
        "sample_ids": sample_ids_json,
        "basename": basename_markdup,
        "batch_id": batch_id,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "input_dir": pipeline_dir,
        "build": assembly,
        "include_unmapped": include_unmapped,
        "cpus": cpus_bamqc,
        "ram": ram_bamqc,
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "batchqc":
        config_step = {
        "submit_method": method_names["batchqc"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "mode" : mode_batch_qc,
        "sample_ids": sample_ids_json,
        "basename": basename_markdup,
        "batch_id": batch_id,
        "input_dir": pipeline_dir_s3,
        "output_dir": batch_qc_dir_s3,
        "control_batch_ids":control_batch_ids,
        "excel_filepath":excel_filepath,
        "tel_chat": tel_chat,
        "tel_token": tel_token,
        "assembly": assembly,
        "endpoint": endpoint,
        "jobs":jobs_batch_qc,
        "cpus": cpus_batch_qc,
        "ram": ram_batch_qc,
        "contamination_thresh":contamination_thresh
    }
    if pipeline_step == "prs":
        config_step = {
        "submit_method": method_names["prs"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "mode_prs" : mode_prs,
        "batchids_prs": batchids_prs,
        "wait": "true",
    }

    return config_step



final_json = []

for s in steps:
    final_json.append(submit_methods(s,cluster,mongo_cluster))

with open(f"{batch_id}_clus-{cluster}_mongo-{mongo_cluster}_stage1.json", 'w') as f:
    json.dump(final_json, f, indent=1)
