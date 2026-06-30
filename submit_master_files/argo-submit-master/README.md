Run pipeline-v3.0 with configuration from the JSON file.

## Usage

```bash
python3 main.py --help
```

### 🚀 Launch Parameters


|Option|Description|Default Value|Required|
|:---|:---|:---|:---|
|`--config`|Path to JSON file with workflow parameters|—|Yes|
|`--debug-mode`|Enable verbose logging (flag)|`--no-debug-mode`|No|
|`--contour`|Runtime environment: `prod` (production) or `dev` (development)|`prod`|No|
|`--help`|Show this help message and exit|—|No|

### Basic Command

```bash
python3 main.py --config <PATH_TO_CONFIG>
```

### Configuration File `config.json`

The `config.json` file contains settings for running a data processing pipeline. Below is a description of each configuration field.

### Configuration Structure

The configuration is an array of objects. Each object contains the following fields:


|Field|Type|Required|Description|
|:---|:---|:---|:---|
|`submit_method`|String|Yes|Job submission method. Example: `submit_cutadapt_s3_mounted_multiple_tubes_delay` (specific method for processing data using Cutadapt and S3 mounting).|
|`k8s_cluster_name`|String|Yes|Name of the Kubernetes cluster where the pipeline runs. Example: `pipeline-v3-3`.|
|`namespace`|String|No|Kubernetes namespace for deploying tasks. Default: `default`.|
|`sample_ids`|Array of objects|Yes|List of sample IDs to process. Each object contains a `sample_id` field. **If an empty list is provided**, the system will automatically fetch sample IDs from the MongoDB collection filtering entries by the `batch_id`, `good` fields.|
|`run_id`|String|cutadapt, fq2bam|Unique identifier for the pipeline run. Example: `49FFE7520`.|
|`batch_id`|String|Yes|Batch identifier for organizing tasks. Example: `batch140325`.|
|`delay_config`|Object|No|Delay settings between tasks. **If an empty object(dict) is provided, the system will automatically set default values.** Contains:\<br\> - `delay` (number): Base delay in seconds. Default: 0\<br\> - `step` (number): Incremental step to increase the delay.Default: 10\<br\> - `chunk_size` (number): Number of tasks to run in parallel before applying the delay. Default: 1|
|`output_dir`|String|Yes|Directory to save results. Example: `/mnt/pipeline-v3.0/david-testing/07-04-2025_2`.|
|[wait](https://argo-workflows.readthedocs.io/en/latest/cli/argo_wait/)|Boolean|No|If `true`, the system will wait for workflow to complete before submitting next workflow. Default: True|
|`only_good`|Boolean|No|If `true`, the system will use only approved samples. Default: False|
|`contour`|String|No|`prod` or `dev`. Default: `prod`|
|`stop_on_error`|Boolean|No (default = `false`)|If `true` and the template runs with `wait` flag, service will stop after one template flow failed. If `false` and the template runs with `wait` flag, service will continue submitting next templates|

### Example Configuration

s3://pipeline-v3.0/argo-configs/example\_config.json

```json
[
    {
        "submit_method": "submit_cutadapt_s3_mounted_multiple_tubes_delay",
        "k8s_cluster_name": "pipeline-v3-3",
        "namespace": "default",
        "sample_ids": [
            {"sample_id": "uq6915"},
            {"sample_id": "tm9114"},
            {"sample_id": "wn7342"}
        ],
        "run_id": "49FFE7520",
        "batch_id": "batch140325",
        "delay_config": {
            "delay": 10,
            "step": 1,
            "chunk_size": 1
        },
        "output_dir": "/mnt/pipeline-v3.0/david-testing/07-04-2025_2",
        "wait": true,
		"stop_on_error": true
    },
    {
        "submit_method": "submit_cutadapt_s3_mounted_multiple_tubes_delay",
        "k8s_cluster_name": "pipeline-v3-3",
        "namespace": "default",
        "sample_ids": [],
        "run_id": "49FFE7520",
        "batch_id": "batch140325",
        "delay_config": {},
        "output_dir": "/mnt/pipeline-v3.0/david-testing/07-04-2025_2",
        "wait": true,
        "only_good": true,
		"stop_on_error": false # not required really, but you can set it clearly
    },
    {
        "submit_method": "submit_fq2bam_s3_mounted_multiple_tubes_delay",
        "k8s_cluster_name": "pipeline-v3-3",
        "namespace": "default",
        "sample_ids": [
            {"sample_id": "uq6915"},
            {"sample_id": "tm9114"},
            {"sample_id": "wn7342"}
        ],
        "run_id": "49FFE7520",
        "batch_id": "batch140325",
        "delay_config": {
            "delay": 10,
            "step": 1,
            "chunk_size": 1
        },
        "input_dir": "/mnt/pipeline-v3.0/david-testing/07-04-2025_2",
        "output_dir": "/mnt/pipeline-v3.0/david-testing/08-04-2025_2",
        "assembly": "hg19",
        "markdup": "no",
        "cpus": 2,
        "ram": 3,
        "bwa_version": 1,
        "bam_suffix_markdup": "markdup",
        "pair_end": "yes",
        "split_per_chr": "no"
    },
    {
        "submit_method": "submit_haplotypecaller_gvcf2vcf_full_multiple_tubes",
        "k8s_cluster_name": "pipeline-v3-3",
        "namespace": "default",
        "wait": true,
        "batch_id": "batch140325",
        "sample_ids": [
            {"sample_id": "uq6915"},
            {"sample_id": "tm9114"},
            {"sample_id": "wn7342"}
        ],
        "input_dir_s3": "/mnt/pipeline-v3.0/batch140325",
        "output_dir_s3": "/mnt/pipeline-v3.0/david-testing",
        "basename_called_vcf": "called.filtered",
        "assembly": "hg19",
        "dbsnp_vcf": "/mnt/pipeline-v3.0/db/hg19/dbsnp.target_positions.hg19.vcf",
        "dbsnp": "/mnt/pipeline-v3.0/db/hg19/dbsnp.target_positions.hg19.vcf.gz",
        "ref": "/mnt/pipeline-v3.0/ref/hg19/hg19.fa",
        "regions_without_homopolymers": "/mnt/pipeline-v3.0/db/hg19/regions_without_homopolymer.hg19.bed"
    }
]
```

### Local Installation and Setup

#### Yandex Cloud CLI (yc)

```bash
# Install yc
curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash

# Configure profile
yc config profile create sa-profile
yc config set service-account-key authorized_key.json  # Replace with your key
yc config set cloud-id b1gi58g81vplnoa8tdbt           # Replace with your cloud ID
yc config set folder-id b1ggjgcj0ci3dr0lohs6         # Replace with your folder ID
```

#### kubectl Installation

Follow official guide: 

https://kubernetes.io/ru/docs/tasks/tools/install-kubectl/

```bash
# Install latest version
curl -LO https://dl.k8s.io/release/`curl -LS https://dl.k8s.io/release/stable.txt`/bin/linux/amd64/kubectl

# OR install specific version (v1.32.0)
curl -LO https://dl.k8s.io/release/v1.32.0/bin/linux/amd64/kubectl

# Make executable and move to PATH
chmod +x ./kubectl
sudo mv ./kubectl /usr/local/bin/kubectl

# Verify installation
kubectl version --client
```

#### Argo Workflows CLI

Download from releases: 

https://github.com/argoproj/argo-workflows/releases/

```bash
# Install v3.6.5
curl -sLO "https://github.com/argoproj/argo-workflows/releases/download/v3.6.5/argo-Linux-amd64.gz"
gunzip "argo-Linux-amd64.gz"
chmod +x "argo-Linux-amd64"
sudo mv "./argo-Linux-amd64" /usr/local/bin/argo

# Verify installation
argo version

# Example workflow submission
argo submit --from workflowtemplate/delightful-rhino --wait
```

### 🐳 Docker Operations

Build Image

```bash
sudo docker build . -t "cr.yandex/crpghhvv7nt3gi67ggjn/<name>:<version>"
```

Run Container (Interactive)

```bash
sudo docker run "cr.yandex/crpghhvv7nt3gi67ggjn/<name>:<version>" \
python3 main.py --debug-mode \
--config /mnt/pipelinve-v3.0/configs/example_config.json
```

Push to Registry

```bash
sudo docker push "cr.yandex/crpghhvv7nt3gi67ggjn/<name>:<version>"
```

### Argo template

k8s cluster: [pipeline-v3-3](https://console.yandex.cloud/folders/b1ggjgcj0ci3dr0lohs6/managed-kubernetes/cluster/catu34ruhisrbiml19um/overview)

template name: [argo-submit-workflow](https://158.160.180.54:2746/workflow-templates/default/argo-submit-workflow)

Lockbox Credentials: [pipeline-v3-3](https://console.yandex.cloud/folders/b1ggjgcj0ci3dr0lohs6/lockbox/secret/e6qs6o23fovjekcpri1h/overview)

```yaml
spec:
  templates:
    - name: argo-submit
      inputs:
        parameters:
          - name: config_path
      outputs: {}
      metadata: {}
      container:
        name: main
        image: cr.yandex/crpghhvv7nt3gi67ggjn/argo_submit:<tag>
        command:
          - python
        args:
          - main.py
          - --config
          - /mnt/pipeline-v3.0/{{inputs.parameters.config_path}}
        resources: {}
        volumeMounts:
          - name: pipeline-v3-0
            mountPath: /mnt/pipeline-v3.0
  entrypoint: argo-submit
  arguments: {}
  volumes:
    - name: pipeline-v3-0
      persistentVolumeClaim:
        claimName: pipeline-v3.0-pvc-static
  ttlStrategy:
    secondsAfterCompletion: 300
  podGC:
    strategy: OnPodCompletion
```

### CI

k8s cluster: [docker-services](https://console.yandex.cloud/folders/b1ggjgcj0ci3dr0lohs6/managed-kubernetes/cluster/cat7u22rns6gbfkn921v/overview)

prod template name: [argo-submit-master-prod](https://130.193.45.193:2746/workflow-templates/argo-events/argo-submit-master-prod)

dev template name:

Event Source: [gitlab-events](https://130.193.45.193:2746/event-sources/argo-events/gitlab-events)

prod sensor: [argo-submit-master-sensor](https://130.193.45.193:2746/sensors/argo-events/argo-submit-master-sensor)

Lockbox Credentials: [ARGO CI](https://console.yandex.cloud/folders/b1ggjgcj0ci3dr0lohs6/lockbox/secret/e6qr9fnudo6uu7iegr1r/overview)