
10-gVCF2VCF
Обновлено 26 февраля 2026, 13:03

Step Description
Role and Importance: The step of GVCF 2 VCF is the continuation to variant calling after haplotype caller. the gvcf files are converted into vcf files, our final form, which undergoes a series of quality filtrations and annotation by dbsnp. Also transfers gvcf and vcf to main storage.

Tools or algorithms: GATK GenotypeGVCFs for format converting.

Source Code & Workflow
GitLab Main Repository: gvcf2vcf-s3-mounted

GitLab Branch: main

GitLab Directory: gvcf2vcf-s3-mounted. See Page In Gitlab

Argo Reference Workflow: gvcf2vcf-s3-mounted. See Template in Argo

Argo Master Workflow: gvcf2vcf-s3-mounted-multiple-tubes. See Template in Argo

EXAMPLE

Inputs & Outputs
Overall volume
680-750 tubes (Good samples that are used in imputation)

Input:
GVCF:

name: {tubeid}.{batchid}.hg19.g.vcf.gz{.tbi}

Format: GVCF.gz

Avg size: 2 MB >

Destination: pipeline-v3.0/{batchid}/{tubeid}/gvcf/

Output:
GVCF: (Transfer to main storage)

name: {tubeid}.{batchid}.hg19.g.vcf.gz{.tbi}

Format: GVCF.gz

Avg size: 2 MB >

Destination: genotek-testing/data/{tubeid}/gvcf/

Called VCF:

name: {tubeid}.{batchid}.called.filtered.hg19.vcf.gz{.tbi}

Format: VCF.gz

Avg size: 50 MB >

Destination: pipeline-v3.0/{batchid}/{tubeid}/vcf/ + genotek-testing/data/{tubeid}/vcf/

Execution Environment
Workflow Orchestration System:
Cluster: New Argo/K8

Node group: fq2bam

Resource usage (per pod): 5 CPU / 20 RAM

Environmental variables (Input parameters):
SAMPLE_IDS: Json with delays. See Delays.

BATCH_ID: batchid that was assigned. It takes this format: batchddmmyy (ex. batch260625)

BASENAME_CALLED_VCF: Basename for final output vcf. Default is "called.filtered"

INPUT_DIR_S3: path for gvcf. Default is: s3://pipeline-v3.0/{batchid}

OUTPUT_DIR_S3: path for called vcf. Default is: s3://pipeline-v3.0/{batchid}

PLOIDY_DIR_S3 : path for ploidy for imputation report, to determine ploidy num for sample. Default is: s3://pipeline-v3.0/batch_QC

BUILD: genomic assembly to align by: hg19 or hg38 (default for now is hg19)

RECALIBRATED: (yes/no) whether it's markdup only (default) or also recalibrated. Default is "no"

CPUS: Number of CPUS to use for pod

RAM: RAM to use for pod

CHROMOSOMES_IN_PARALLEL: number of parallel jobs, within each one chr is running. Default is 5

DBSNP_VCF: (keep default) name of dbsnp vcf used for annotation inside this dir: s3://pipeline-v3.0/db/{ASSEMBLY}/.

REF: (Redundant) reference fasta

REGIONS_WITHOUT_HOMOPOLYMERS: (keep default) s3 path to corresponding bed .

delay: just a filler redundant parameter. (ignore)

Performance Metrics:
Per single unit: ~5-10 min

Per full batch: ~30-45 min

Additional Notes
Dependencies: Haplotypecaller.

Known edge cases or failure causes: None.

