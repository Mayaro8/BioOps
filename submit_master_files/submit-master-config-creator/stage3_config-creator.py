import json
import pandas as pd
import argparse
import csv
parser = argparse.ArgumentParser(description="Argument inputs for bioinformatics stage")

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
    steps = ["beagle","inher","hla","hla_parser","lk","apoe","transfer_bam","y","deep_mito","anal","batch_report","final_checker"]
elif steps[0] == "no_bgl":
    steps = ["inher","hla","hla_parser","lk","apoe","transfer_bam","y","deep_mito","anal","batch_report","final_checker"]

print(steps)
cluster = args.cluster_name
mongo_cluster = args.mongo_cluster_name

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
output_storage_folder=var_list["output_storage_folder"]
pipeline_env = var_list["env"]
tel_chat = var_list["tel_chat"]
tel_token = var_list["tel_token"]

delay = var_list["delay"]
step = var_list["step"]
chunk_size = var_list["chunk_size"]

sample_ids_str = var_list["samples_ids_str"]
sample_ids_json = [{"sample_id": s.strip()} for s in sample_ids_str.split(",")]
sample_ids_pylist = json.dumps(sample_ids_str.split(','))

sample_ids_hla = [{"tubeid": s.strip(),"filename":f"{s.strip()}.{batch_id}.{basename_markdup}.{assembly}.bam"} for s in sample_ids_str.split(",")]
sample_ids_inh = [{"tubeid":s.strip(),"vcf_path":f"{output_storage_folder}/{s.strip()}/vcf/{s.strip()}.{batch_id}.{basename_called}.{assembly}.vcf.gz",
"vcf_idx_path":f"{output_storage_folder}/{s.strip()}/vcf/{s.strip()}.{batch_id}.{basename_called}.{assembly}.vcf.gz.tbi",
"gvcf_path":f"{output_storage_folder}/{s.strip()}/gvcf/{s.strip()}.{batch_id}.{assembly}.g.vcf.gz",
"gvcf_idx_path":f"{output_storage_folder}/{s.strip()}/gvcf/{s.strip()}.{batch_id}.{assembly}.g.vcf.gz.tbi",
"output_path":f"{output_storage_folder}/{s.strip()}/mass_results/diseases_updated/"} for s in sample_ids_str.split(",")]


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

#########################
# beagle
beagle_chunk_size = var_list["beagle_chunk_size"]

# hla
local_input_hla = var_list["local_input_hla"]
output_hla_s3 = var_list["output_hla_s3"]
mnt_bucket_hla = var_list["mnt_bucket_hla"]
input_hla_s3 = var_list["input_hla_s3"]


# hla parser (comma list)
mongo_db_hla = var_list["mongo_db_hla"]
jobs_hla_parser = var_list["jobs_hla_parser"]

# lk
mode_lk = var_list["mode_lk"]

# inheritance
clinvar_db  = var_list["clinvar_db"]

# Transfer Bam
output_main_dir=var_list["output_main_dir"]

# deep-mito (comma list)
chunk_size_deep_mito = var_list["chunk_size_deep_mito"]
jobs_deep_mito = var_list["jobs_deep_mito"]
mode_deep_mito = var_list["mode_deep_mito"]
version_deep_mito = var_list["version_deep_mito"]
tree_deep_mito = var_list["tree_deep_mito"]
ref_type = var_list["ref_type"]
hp_threshold_deep_mito = var_list["hp_threshold_deep_mito"]
dedup_deep_mito = var_list["dedup_deep_mito"]
hotspot_deep_mito = var_list["hotspot_deep_mito"]

# final_checker
delete_files= var_list["delete_files"]
copy_bad= var_list["copy_bad"]
bad_only= var_list["bad_only"]
jobs_checker=var_list["jobs_checker"]

#########################
def submit_methods(pipeline_step,cluster,mongo_cluster):
    if pipeline_step == "beagle":
        config_step = {
        "submit_method": method_names["beagle"],
        "k8s_cluster_name": "analysis-pipeline-test",
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "date_batch_id":batch_date_id,
        "bucket":output_main_dir,
        "chunk_size":beagle_chunk_size,
        "wait": "true",
        "only_good": "false"
    }

    if pipeline_step == "hla":
        config_step = {
        "submit_method": method_names["hla"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_hla,
        "local_input_hla": local_input_hla,
        "input_hla_s3" : input_hla_s3,
        "output_hla_s3": output_hla_s3,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "mnt_bucket_hla": mnt_bucket_hla,
        "reference": assembly,
        "basename" : basename_markdup,
        "env" : pipeline_env,
        "wait": "true",
        "only_good": "false"
    }
    if pipeline_step == "hla_parser":
        config_step = {
        "submit_method": method_names["hla_parser"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "mongo_db_hla": mongo_db_hla,
        "jobs_hla_parser": jobs_hla_parser,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"
    }
    if pipeline_step == "lk":
        config_step = {
        "submit_method": method_names["lk"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "sample_ids" : sample_ids_json,
        "date_batch_id":batch_date_id,
        "batch_id":batch_id,
        "called_basename": basename_called,
        "assembly": assembly,
        "split_mode": mode_lk,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "inher":
        config_step = {
        "submit_method": method_names["inher"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "batch_id": batch_id,
        "basename": basename_called,
        "bucket": output_main_dir,
        "assembly" : assembly,
        "clinvar_db": clinvar_db,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "apoe":
        config_step = {
        "submit_method": method_names["apoe"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "sample_ids": sample_ids_json,
        "env" : pipeline_env,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "anal":
        config_step = {
        "submit_method": method_names["anal"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "sample_ids" : sample_ids_json,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }

    if pipeline_step == "transfer_bam":
        config_step = {
        "submit_method": method_names["transfer_bam"],
        "k8s_cluster_name": cluster,
        "namespace": namespace,
        "batch_id": batch_id,
        "sample_ids": sample_ids_json,
        "dest_env":output_main_dir,
        "tel_token": tel_token,
        "tel_chat": tel_chat,
        "wait": "true",
    }
    
    if pipeline_step == "y":
        config_step = {
        "submit_method": method_names["y"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "batch_id":batch_id,
        "env":pipeline_env,
        "input_mode":"batch",
        "tel_chat": tel_chat,
        "tel_token": tel_token,
        "input_tubes": "",
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "deep_mito":
        config_step = {
        "submit_method": method_names["deep_mito"],
        "k8s_cluster_name": mongo_cluster,
        "namespace": namespace,
        "sample_ids":sample_ids_json,
        "chunk_size_deep_mito": chunk_size_deep_mito,
        "jobs_deep_mito": jobs_deep_mito,
        "mode_deep_mito" : mode_deep_mito ,
        "version_deep_mito" : version_deep_mito,
        "tree_deep_mito" : tree_deep_mito,
        "ref_type" : ref_type,
        "build": assembly,
        "hp_threshold_deep_mito" : hp_threshold_deep_mito, 
        "dedup_deep_mito" : dedup_deep_mito, 
        "hotspot_deep_mito" : hotspot_deep_mito, 
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "false",
        "only_good": "true"        
    }
    if pipeline_step == "batch_report":
        config_step = {
        "submit_method": method_names["batch_report"],
        "k8s_cluster_name": "analysis-pipeline-test",
        "namespace": namespace,
        "batch_id": batch_date_id,
        "tel_chat": tel_chat,
        "tel_token": tel_token,
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    if pipeline_step == "final_checker":
        config_step = {
        "submit_method": method_names["final_checker"],
        "k8s_cluster_name": "pipeline-v3-4",
        "namespace": namespace,
        "batch_id": batch_id,
        "assembly": assembly,
        "run_num": run_number,
        "delete": delete_files,
        "copy_bad": copy_bad,
        "bad_only": bad_only,
        "jobs": jobs_checker,
        "tel_chat":tel_chat,
        "tel_token":tel_token,        
        "delay_config": {
            "delay": delay,
            "step": step,
            "chunk_size": chunk_size
        },
        "wait": "true",
        "only_good": "true"        
    }
    return config_step

final_json = []

for s in steps:
    final_json.append(submit_methods(s,cluster,mongo_cluster))

with open(f"{batch_id}_clus-{cluster}_mongo-{mongo_cluster}_stage3.json", 'w') as f:
    json.dump(final_json, f, indent=1)
