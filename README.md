# BioOps

BioOps is a multi-agent assistant for bioinformatics operations, including knowledge retrieval, Kubernetes cluster health monitoring, pipeline status reporting, Submit Master operations, code review, and operational alerts.

## Documentation

Detailed project documentation is available in `docs/`:

- `docs/README.md` — full project overview.
- `docs/DESIGN.md` — architecture and design notes.
- `docs/assignment.md` — Russian assignment specification.
- `docs/assignment.en.md` — English assignment specification.

## Current agents include

- Knowledge Agent — answers questions from indexed project documentation.
- Cluster Health Agent — checks Kubernetes pod health, logs, running steps, cost, and ETA.
- Review Agent — reviews local repositories, GitHub repositories, PRs, open PRs, and branch comparisons.
- Submit Master Agent — prepares, launches, monitors, reports, and safely retries Submit Master workflows.
- General fallback agent — handles greetings, unclear requests, and unsupported tasks.

---

## 1. Requirements

```text
Git
Docker
Docker Compose
kubectl, only for Cluster Health Agent and Submit Master Agent
A running Kubernetes cluster, only for Cluster Health Agent and Submit Master Agent
Argo Workflows, only for Submit Master Agent
Azure OpenAI credentials, for Knowledge Agent, LLM router, and LLM review
GitHub token, for GitHub Review Agent
Bitrix24 webhook, optional for Health Monitor alerts and Submit Master reports
```

---

## 2. One-time setup

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
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

Do not commit `.env`.

---

## 3. Build and launch BioOps

```bash
docker compose build bioops
docker compose up -d qdrant
docker compose run --rm bioops python -m bioops.rag.ingest
docker compose run --rm bioops python -m pytest
docker compose run --rm bioops python -m bioops.main
```

Expected startup:

```text
BioOps CLI started. Type 'exit' to quit.
You:
```

---

## 4. Knowledge Agent

Purpose:

```text
Answer questions from indexed files in docs/.
```

Example prompts:

```text
Explain pipeline-v3.0 steps.
What does bam to gvcf output?
Which step takes a gvcf file as input?
```

---

## 5. Review Agent

Purpose:

```text
Read-only code review for local repos, GitHub repos, PRs, open PRs, and branch comparisons.
```

Example prompts:

```text
Review path=/app
Review repo=Mayaro8/BioOps
Check open PRs repo=Mayaro8/BioOps
Review repo=Mayaro8/BioOps pr=1
Review repo=Mayaro8/BioOps base=main head=feature/example
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

Example prompts:

```text
Check Kubernetes cluster health.
Are any pods failing?
Which pipeline steps are running?
Show recent Kubernetes errors.
What is the ETA for the running pipeline?
How much is the current cluster run costing?
```

Note:

```text
The Cluster Health Agent is read-only.
It reports pod health and errors.
It does not restart pods.
Submit Master retry belongs to the Submit Master Agent and D5 job.
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

Bitrix configuration:

```env
ALERT_CHANNEL=bitrix
BITRIX_WEBHOOK_URL=https://your-domain.bitrix24.com/rest/USER_ID/WEBHOOK_CODE
BITRIX_DIALOG_ID=chat123
```

Run manually:

```bash
docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```

---

## 8. Submit Master Agent

Purpose:

```text
Prepare, launch, monitor, report, and safely retry Submit Master workflows through BioOps.
```

The Submit Master Agent covers Epic D:

```text
D1 — generate original-compatible Submit Master configuration.
D2 — prepare and launch Submit Master through Argo.
D3 — monitor Submit Master workflow status, progress, errors, logs, runtime, cost, and ETA where available.
D4 — report failed Submit Master workflow pods/nodes to Bitrix24.
D5 — safely retry failed Submit Master workflows with retry limits and safety checks.
```

Useful files:

```text
src/bioops/agents/submit_master_agent.py
src/bioops/tools/argo_ui_launcher.py
src/bioops/tools/argo_workflow_monitor.py
src/bioops/jobs/submit_master_d3_bitrix_report.py
src/bioops/jobs/submit_master_d4_failure_bitrix_report.py
src/bioops/jobs/submit_master_d5_retry_bitrix_report.py
k8s/argo/local/bioops-submit-master-local.yaml
k8s/argo/real/bioops-submit-master-real.yaml
k8s/argo/company/bioops-submit-master-company.yaml
```

Example prompts:

```text
Launch Submit Master.
Open Submit Master in Argo.
Show Submit Master progress.
Report failed Submit Master pods to Bitrix.
Retry failed Submit Master workflows safely.
```

Safety:

```text
Submit Master retry is guarded.
Known deterministic/configuration failures should not be retried automatically.
Retries are capped.
Resubmitted workflows are annotated with retry metadata.
Active retries should not be duplicated.
```

---

## 9. BioOps API and Bitrix24 Kubernetes mode

Purpose:

```text
Run BioOps as a Kubernetes API service that can receive Bitrix24 messages and send responses back to Bitrix24.
```

Useful files:

```text
src/bioops/api/bitrix_app.py
k8s/bioops-api/deployment.yaml
k8s/bioops-api/service.yaml
k8s/bioops-api/ingress.yaml
k8s/bioops-dev.yaml
k8s/bioops-argo-rbac.yaml
```

Required Kubernetes secret:

```bash
kubectl create secret generic bioops-api-secrets \
  -n bioops-dev \
  --from-literal=BITRIX_WEBHOOK_URL='https://your-domain.bitrix24.com/rest/USER_ID/WEBHOOK_CODE' \
  --from-literal=BITRIX_DIALOG_ID='chat123'
```

Apply manifests:

```bash
kubectl apply -f k8s/bioops-api/deployment.yaml
kubectl apply -f k8s/bioops-api/service.yaml
kubectl apply -f k8s/bioops-api/ingress.yaml
```

Health check:

```bash
curl https://YOUR_HOST/health
```

Bitrix message test:

```bash
curl -X POST https://YOUR_HOST/bitrix/message \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello from Bitrix","dialog_id":"chat123"}'
```

---

## 10. Minimal demo sequence

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

## 11. What are the different functionalities of the submit master agent

First it would launch the Argo UI taking the bioinformatician into the submit master, completing D1. For D2, the agent launches Config Creator, a package already developed that creates config for the submit master. For D3-D4, it send a Bitrix24 report to the user. For D5, it restarts the pod. 

To test the functionality, the agent must be deployed onto K8s and then accessed through Bitrix 24, after that a command through Bitrix24, will connect to Argo and read or perform the action. For now, it is manually launched on Argo and the messages it send are checked through Bitrix24. 

After deploying the image of the agent on K8s, I would need to do some more tests to check how it works.
