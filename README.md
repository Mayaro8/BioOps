# BioOps

BioOps is a multi-agent assistant for bioinformatics operations, including knowledge retrieval, Kubernetes cluster health monitoring, pipeline status reporting, code review, and operational alerts.

## Documentation


Detailed project documentation is available in [`docs/`](docs/):

- [`docs/README.md`](docs/README.md) — full project overview
- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture and design notes
- [`docs/assignment.md`](docs/assignment.md) — assignment specification
- [`docs/assignment.en.md`](docs/assignment.en.md) — English assignment specification

- [Internship assignment (English)](docs/assignment.en.md) — goals, requirements, architecture, stages, and acceptance criteria.
- [Задание на практику (Russian)](docs/assignment.md) — Russian version of the document above.

## Current agents include:

* Knowledge Agent — answers questions from indexed project documentation.
* Cluster Health Agent — checks Kubernetes pod health, logs, running steps, cost, and ETA.
* Review Agent — reviews local repositories, GitHub repositories, PRs, open PRs, and branch comparisons.
* General fallback agent - for when the Azure key doesn't come up with a suitable agent to relay the prompt to.
---

## 1. Requirements

```text
Git
Docker
Docker Compose
kubectl, only for Cluster Health Agent
A running Kubernetes cluster, only for Cluster Health Agent
Azure OpenAI credentials, for Knowledge Agent, LLM router, and LLM review
GitHub token, for GitHub Review Agent
Bitrix24 webhook, optional for Health Monitor alerts
```

---

## 2. One-time setup for all agents

Clone the repository:

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
```

Create local environment file:

```bash
cp .env.example .env
nano .env
```

Minimum useful `.env` shape:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=your_chat_deployment

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=bioops_knowledge

GITHUB_TOKEN=your_github_token

ALERT_CHANNEL=console
BITRIX_WEBHOOK_URL=
BITRIX_DIALOG_ID=
```

For Bitrix24 alerts:

```env
ALERT_CHANNEL=bitrix
BITRIX_WEBHOOK_URL=https://your-domain.bitrix24.com/rest/USER_ID/WEBHOOK_CODE
BITRIX_DIALOG_ID=chat123
```

Do not commit `.env`.

---

## 3. Build and launch BioOps

Build the BioOps container:

```bash
docker compose build bioops
```

Start Qdrant for the Knowledge Agent:

```bash
docker compose up -d qdrant
```

Ingest documentation into Qdrant:

```bash
docker compose run --rm bioops python -m bioops.rag.ingest
```

Run tests:

```bash
docker compose run --rm bioops python -m pytest
```

Start the CLI:

```bash
docker compose run --rm bioops python -m bioops.main
```

Expected startup:

```text
BioOps CLI started. Type 'exit' to quit.
You:

# Agent usage

## 4. Knowledge Agent

Purpose:

```text
Answer questions from indexed files in docs/.
```

Required before use:

```bash
docker compose up -d qdrant
docker compose run --rm bioops python -m bioops.rag.ingest
docker compose run --rm bioops python -m bioops.main
```

Example prompts:

```text
Explain pipeline-v3.0 steps.
```

Expected answer shape:

```text
pipeline-v3.0 includes the following documented steps:
1. bam-to-gvcf
2. gvcf-to-vcf
...
```

```text
What does bam to gvcf output?
```

Expected answer shape:

```text
bam-to-gvcf outputs a GVCF file.
```

```text
Which step takes a gvcf file as input?
```

Expected answer shape:

```text
gvcf-to-vcf takes a GVCF file as input.
```

```text
Based on the indexed documentation, what does gvcf to vcf do?
```

Expected answer shape:

```text
The indexed documentation says that gvcf-to-vcf converts GVCF input into VCF output.
```

Troubleshooting:

```text
If answers are empty or generic, rerun ingestion.
If Qdrant is unreachable, check docker compose ps.
```

---

## 5. Review Agent

Purpose:

```text
Read-only code review for local repos, GitHub repos, PRs, open PRs, and branch comparisons.
```

Required for GitHub review:

```env
GITHUB_TOKEN=your_github_token
```

Required for LLM patch review:

```env
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=...
AZURE_OPENAI_CHAT_DEPLOYMENT=...
```

Start CLI:

```bash
docker compose run --rm bioops python -m bioops.main
```

### Case 1 — local repository review

Prompt:

```text
Review path=/app
```

Expected answer shape:

```text
Local Repository Review Report

Status: ok
Path: /app

Changed files:
- ...

Found issues:
- ...

Risks:
- ...

Suggestions:
- Run pytest.
- Add tests for changed agent/tool behavior.
```

### Case 2 — GitHub repository overview

Prompt:

```text
Review repo=Mayaro8/BioOps
```

Expected answer shape:

```text
GitHub Repository Review Report

Repository: Mayaro8/BioOps
Status: ok

Repository structure:
- README found
- src/bioops found
- tests found
- Dockerfile found

Risks:
- ...
Suggestions:
- ...
```

### Case 3 — list open pull requests

Prompt:

```text
Check open PRs repo=Mayaro8/BioOps
```

Expected answer shape:

```text
Open Pull Requests Report

Repository: Mayaro8/BioOps

Open PRs:
- PR #1: title
  base: main
  head: feature/example
  changed files: N
  diff size: +A/-D
```

### Case 4 — review one pull request

Prompt:

```text
Review repo=Mayaro8/BioOps pr=1
```

or:

```text
Review https://github.com/Mayaro8/BioOps/pull/1
```

Expected answer shape:

```text
GitHub PR Review Report

Repository: Mayaro8/BioOps
Subject: PR #1: title
Base branch: main
Head branch: feature/example

Changed files:
- src/example.py [modified, +10/-2]

Found issues:
- ...

Risks:
- ...

Suggestions:
- ...

LLM patch review:
1. Verdict: ...
2. Top issues: ...
3. Risks: ...
4. Next steps: ...

Review note:
- No GitHub comments were posted.
- No PR status was modified.
```

### Case 5 — branch comparison

Prompt:

```text
Review repo=Mayaro8/BioOps base=main head=feature/example
```

Expected answer shape:

```text
GitHub Branch Comparison Review

Repository: Mayaro8/BioOps
Base branch: main
Head branch: feature/example

Commits ahead: N
Commits behind: N
Changed files: N

Risks:
- ...

LLM patch review:
...
```

Safety:

```text
The Review Agent is read-only.
It does not approve PRs.
It does not reject PRs.
It does not post comments.
It does not push commits.
```

---

## 6. Cluster Health Agent

Purpose:

```text
Check Kubernetes pod health, running pipeline steps, unhealthy pods, logs, cost, and ETA.
```

The Docker image does not create a Kubernetes cluster. Use an existing cluster, Minikube, or Kind.

For local Minikube testing:

```bash
minikube start
kubectl get nodes
kubectl create namespace bioops
```

Create test pods:

```bash
kubectl run bam-to-gvcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=bam-to-gvcf \
  --command -- sleep 3600
```

```bash
kubectl run gvcf-to-vcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=gvcf-to-vcf \
  --command -- sh -c "echo failed gvcf-to-vcf; exit 1"
```

Check pods:

```bash
kubectl get pods -n bioops
```

Start CLI:

```bash
docker compose run --rm bioops python -m bioops.main
```

### Prompt examples

Prompt:

```text
Check Kubernetes cluster health.
```

Expected answer shape:

```text
Cluster Health Report

Total pods: 2
Running pods: 1
Unhealthy / waiting pods: 1

Currently running pipeline steps:
- bam-to-gvcf: bam-to-gvcf-worker [Running, runtime: ...]

All observed pod statuses:
- bam-to-gvcf: bam-to-gvcf-worker [Running, runtime: ...]
- gvcf-to-vcf: gvcf-to-vcf-worker [Failed, runtime: ...]

Errors:
- gvcf-to-vcf-worker is in phase Failed.
- gvcf-to-vcf-worker log error: failed gvcf-to-vcf

Cost:
- Estimated cost: ...

ETA:
- ...
```

Prompt:

```text
Are any pods failing?
```

Expected answer shape:

```text
Cluster Health Report

Unhealthy / waiting pods: 1

Errors:
- gvcf-to-vcf-worker is in phase Failed.
- gvcf-to-vcf-worker terminated with exit code 1.
```

Prompt:

```text
Which pipeline steps are running?
```

Expected answer shape:

```text
Currently running pipeline steps:
- bam-to-gvcf: bam-to-gvcf-worker [Running, runtime: ...]
```

Prompt:

```text
Show recent Kubernetes errors.
```

Expected answer shape:

```text
Errors:
- gvcf-to-vcf-worker is in phase Failed.
- gvcf-to-vcf-worker log error: failed gvcf-to-vcf
- gvcf-to-vcf-worker terminated with exit code 1.
```

Prompt:

```text
What is the ETA for the running pipeline?
```

Expected answer shape:

```text
ETA:
- bam-to-gvcf: estimated remaining time ...
```

Prompt:

```text
How much is the current cluster run costing?
```

Expected answer shape:

```text
Cost:
- Estimated cost: ...
- Source: ...
- Mode: ...
```

Note:

```text
The Cluster Health Agent is read-only.
It reports pod health and errors.
It does not restart pods.
Restarting failed pods belongs to the Submit Master Agent and should require confirmation.
```

---

## 7. Health Monitor and Bitrix24 alerts

Purpose:

```text
Run Cluster Health Agent without opening the CLI.
Useful for scheduled checks and Bitrix24 demos.
```

Flow:

```text
cron or manual command
↓
scripts/run_cluster_health_monitor.sh
↓
python -m bioops.jobs.cluster_health_monitor
↓
ClusterHealthAgent
↓
AlertTool
↓
console or Bitrix24
```

### Configure Bitrix24

In `.env`:

```env
ALERT_CHANNEL=bitrix
BITRIX_WEBHOOK_URL=https://your-domain.bitrix24.com/rest/USER_ID/WEBHOOK_CODE
BITRIX_DIALOG_ID=chat123
```

For console-only testing:

```env
ALERT_CHANNEL=console
```

### Test Bitrix directly

```bash
docker compose run --rm bioops python - <<'PY'
from bioops.tools.bitrix_tool import BitrixTool

result = BitrixTool().send_message("BioOps Bitrix24 direct test message")
print(result)
PY
```

Expected result:

```text
BitrixSendResult(ok=True, message='Bitrix message sent successfully.', status_code=200)
```

### Test AlertTool through Bitrix

```bash
docker compose run --rm bioops python - <<'PY'
from bioops.tools.alert_tool import AlertTool

result = AlertTool().send_status(
    title="Bitrix test",
    message="BioOps AlertTool test message"
)

print(result)
PY
```

Expected Bitrix message:

```text
[BIOOPS STATUS] Bitrix test
Severity: info
Time: ...

BioOps AlertTool test message
```

### Run Health Monitor manually

```bash
docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```

or:

```bash
bash scripts/run_cluster_health_monitor.sh
```

Expected alert case:

```text
[BIOOPS ALERT] Cluster issue detected
Severity: warning
Time: ...

Cluster Health Report

Total pods: 2
Running pods: 0
Unhealthy / waiting pods: 2

Errors:
- ...
```

Expected running-status case:

```text
[BIOOPS STATUS] Pipeline is running
Severity: info
Time: ...

Cluster Health Report

Running pods: 1
Currently running pipeline steps:
- ...
```

Expected healthy-status case:

```text
[BIOOPS STATUS] Cluster health OK
Severity: info
Time: ...

Cluster Health Report
...
```

### Run every 3 hours

Edit cron:

```bash
crontab -e
```

Add:

```cron
0 */3 * * * cd /home/mayar/bio-ops && bash scripts/run_cluster_health_monitor.sh >> logs/cluster_health_monitor.log 2>&1
```

This runs the health monitor every 3 hours and writes output to:

```text
logs/cluster_health_monitor.log
```

Without Bitrix24:

```text
The monitor still runs.
The report is printed to console/logs.
No Bitrix message is sent.
The monitor should not crash because Bitrix is missing.
```


## 9. Cleanup test Kubernetes pods

```bash
kubectl delete pod bam-to-gvcf-worker -n bioops
kubectl delete pod gvcf-to-vcf-worker -n bioops
```

---

## 10. Minimal full demo sequence

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps

cp .env.example .env
nano .env

docker compose build bioops
docker compose up -d qdrant
docker compose run --rm bioops python -m bioops.rag.ingest
docker compose run --rm bioops python -m pytest
docker compose run --rm bioops python -m bioops.main
```

For Cluster Health / Bitrix demo:

```bash
minikube start
kubectl create namespace bioops

kubectl run bam-to-gvcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=bam-to-gvcf \
  --command -- sleep 3600

kubectl run gvcf-to-vcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=gvcf-to-vcf \
  --command -- sh -c "echo failed gvcf-to-vcf; exit 1"

docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```
