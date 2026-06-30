12-Transfer
Обновлено 18 сентября 2025, 18:10

Step Description
Role and Importance: This step transfers BAM/VCF+GVCF files from pipeline-v3.0 bucket to genotek-testing bucket.

Tools or algorithms: The transfer is perfomed using Bash script with GNU Parallel and Python wrapper for status notifications sending to Telegram bot.

Source Code & Workflow
The system consists of two separate GitLab branches for BAM and VCF+GVCF transfers

GitLab Main Repository: architecture

GitLab Branch:

BAM transfer: bam-transfer-dev (feature/bam-transfer-rework)

GVCF+VCF transfer: vcf-gvcf-transfer-dev (feature/vcf-transfer-rework)

GitLab Directory:

BAM transfer: bam-transfer-s3 See Page In Gitlab

GVCF+VCF transfer: vcf-transfer-s3 See Page In Gitlab

Argo Workflow:

BAM transfer: transfer-bam-s3-dev See Template in Argo

GVCF+VCF transfer: transfer-vcf-s3-dev See Template in Argo

An Argo Workflow is triggered, pointing to the corresponding Docker image (bam-transfer-s3 or vcf-transfer-s3).

Argo executes the main Bash script (transfer_ bam.sh or transfer_gvcf_ vcf.sh ) inside the container.

The script performs a strict pre-flight check to ensure all source files exist.

If the check is successful, it uses GNU Parallel to copy the files concurrently.

Upon completion or failure, the script calls a Python helper to send a status notification to Telegram.

Inputs & Outputs
Overall volume
Up to a full batch

Input:
S3 Files (existence check and source for copy):

BAM: s3://pipeline-v3.0/{batchID}/{tubeID}/fq2bam/markdup/full_bam/

GVCF+VCF**:** s3://pipeline-v3.0/{batchID}/{tubeID}/vcf/ and s3://pipeline-v3.0/{batchID}/{tubeID}/gvcf

Output:
Copied S3 Files:

BAM: s3://genotek-testing/{batchID}/{tubeID}/fq2bam/markdup/full_bam/

GVCF+VCF : s3://genotek-testing/data-test/{tubeID}/vcf/ and/or s3://genotek-testing/data-test/{tubeID}/gvcf/

Telegram Notification: A status message is sent to the chat.

Failure Report File (on S3): A text report is uploaded to s3://pipeline-v3.0/transfer/{bam or vcf}/failed/ upon any failure.

Failed Tubes List (in Telegram): failed_tubes_{batchID}_{bam or vcf}_transfer.txt is attached to error notifications.

Execution Environment
Workflow Orchestration System:
Cluster: Argo

Resource usage (per pod): 8 CPU / 16 GB RAM (requests)

Environmental variables (Input parameters):
The Argo templates accept the following parameters:

SAMPLE_IDS: (Required) A comma-separated string of tube IDs to be processed.

BATCH_ID: (Required) The ID of the batch to be processed.

TELEGRAM_BOT_TOKEN: (Required) The authentication token for the Telegram bot.

TELEGRAM_CHAT_ID: (Required) The ID of the Telegram chat where notifications will be sent.

Other secret variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION) are mounted from the analyze-pipeline-secret-storage.

Performance Metrics:
BAM Transfer: ~100 tubes in 3.5 minutes.
VCF/GVCF Transfer: ~100 tubes in 2.5 minutes.
Additional Notes
Dependencies: These transfers depend on the successful completion of upstream pipeline stages that generate the source BAM, VCF, and GVCF files.

Resilience Improvement: Both transfers script was updated to include a retry mechanism (3 attempts) during the initial source file check. This was done to handle intermittent S3 availability issues that were observed.

 
