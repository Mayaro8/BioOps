# BioOps

---

## 1. Architecture

```text
Browser
   |
   | HTTPS + Basic Auth
   v
LoadBalancer Service
   |
   v
Caddy sidecar
   |
   v
FastAPI /chat
   |
   v
LLM Router
   |
   +-- General Agent
   +-- Knowledge Agent -------> Qdrant
   +-- Cluster Health Agent --> Kubernetes API and Pod logs
   +-- Review Agent ----------> GitHub API or local repository
   +-- Submit Master Agent ---> Argo Workflow CRDs
   +-- Batch Status Agent ----> SQLite database on PVC
   +-- Storage Agent ---------> CSV bucket inventory
```

The public browser interface is the canonical BioOps frontend.

---

## 2. Repository structure

```text
BioOps/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── configs/
│   └── agents.yaml
├── docs/
│   ├── assignment.md
│   ├── assignment.en.md
│   └── DESIGN.md
├── src/bioops/
│   ├── agents/
│   ├── api/
│   ├── jobs/
│   ├── rag/
│   └── tools/
├── deploy/k8s/
│   ├── config/
│   ├── qdrant/
│   ├── bioops-api/
│   ├── batch-status/
│   ├── cluster-health/
│   └── kustomization.yaml
└── deploy/argo/
    ├── knowledge-ingest-template.yaml
    ├── submit-master-template.yaml
    ├── workflow-ci.yaml
    └── kustomization.yaml
```

---

## 3. Current agents

### General Agent

Handles greetings, unclear questions, and unsupported requests.

### Knowledge Agent

Answers questions from indexed project documentation stored in Qdrant.

Example:

```text
Explain the BioOps orchestrator.
```

### Cluster Health Agent

Reads live Kubernetes data and reports:

- Pod phases;
- container readiness;
- restarts;
- recent errors;
- active pipeline steps identified by `pipeline_step` labels;
- runtime for active pipeline Pods;
- ETA where configured;
- cost where available.

Example:

```text
Check cluster health.
```

The Cluster Health Agent uses a second LLM routing layer to choose a bounded
read-only report. It separates BioOps infrastructure Pods from labeled pipeline
Pods and reports pod phases and active steps as counts and percentages. A
30-minute monitor sends analyzed Pod errors to the browser, and an hourly
monitor sends the full health report. It never restarts Pods.

### Review Agent

Performs read-only reviews of:

- local repositories;
- GitHub repositories;
- pull requests;
- open pull requests;
- branch comparisons.

Example:

```text
Review the Mayaro8/BioOps repository and identify the main engineering risks.
```

The Review Agent does not approve, reject, comment on, or modify pull requests.

### Submit Master Agent

Supports explicit batch, sample, and workflow operations through Argo
Workflows.

Epic D consists of:

```text
D1 — generate a Submit Master configuration
D2 — launch Submit Master
D3 — aggregate status, progress, step distribution, runtime, cost, and ETA
D4 — report failed Pods or workflow nodes for a selected Workflow
D5 — safely retry a failed sample Workflow after exact confirmation
```

The current repository contains a demonstration WorkflowTemplate at:

```text
deploy/argo/submit-master-template.yaml
```

The demo contains two tasks:

```text
config-creator
      |
      v
submit-master
```

The current template demonstrates Argo scheduling, parameter handling, and task-to-task output passing.

It is not yet the real production Submit Master package.

### Batch Status Agent

Reads batch and workflow status from:

```text
/data/bioops_batch_status.sqlite3
```

The database is stored on a Kubernetes PVC.

### Storage Agent

Reads CSV bucket inventory data and reports:

- object count;
- total size;
- prefixes;
- file extensions;
- storage classes;
- filtered inventory summaries.

---

## 4. Current container image

The currently deployed BioOps API and Submit Master image tag is:

```bash
IMAGE="cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:submit-master-20260715-192759"
```

Scheduled monitors retain their own pinned, tested image tags. Check image
references before deployment:

```bash
grep -RIn \
  'cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:' \
  deploy
```

---

## 5. Requirements

Local tools:

```text
Git
Docker
Docker Compose
Yandex Cloud CLI
kubectl
Argo CLI
```

Cluster requirements:

```text
Kubernetes namespace: bioops-dev
Argo Workflows installed
PersistentVolume support
Yandex Container Registry access
fastmri-cpu worker nodes
ServiceAccount with required RBAC
```

The current workloads use:

```yaml
serviceAccountName: bioops-student
```

Scheduling configuration:

```yaml
nodeSelector:
  genoteknodetype: fastmri-cpu

tolerations:
  - key: yandex.cloud/preemptible
    operator: Equal
    value: "true"
    effect: NoSchedule
```

---

## 6. Clone and select the branch

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps

git fetch --all --prune
git switch ifra-final
git pull --ff-only
```

Confirm:

```bash
git branch --show-current
git status
```

---

## 7. Configure Yandex Container Registry

Configure the Yandex Docker credential helper:

```bash
yc config profile list
yc config list
yc container registry configure-docker
```

Verify:

```bash
grep -A5 -B2 '"credHelpers"' ~/.docker/config.json
```

Expected configuration:

```json
{
  "credHelpers": {
    "cr.yandex": "yc"
  }
}
```

When the credential helper is configured, do not use a separate `docker login cr.yandex` command.

---

## 8. Build and push the image

```bash
IMAGE="cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:submit-master-20260715-192759"

docker build -t "$IMAGE" .
docker push "$IMAGE"
```

A successful push returns a registry digest:

```text
digest: sha256:...
```

---

## 9. Kubernetes secrets

Never commit credentials to Git.

The main application Secret is:

```text
bioops-secrets
```

It should contain the required Azure OpenAI and GitHub values.

Example:

```bash
read -rsp "Azure OpenAI API key: " AZURE_OPENAI_API_KEY
echo

read -rsp "GitHub token: " GITHUB_TOKEN
echo
```

Set the non-secret Azure values:

```bash
AZURE_OPENAI_ENDPOINT="https://YOUR-RESOURCE.openai.azure.com/"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"
AZURE_OPENAI_CHAT_DEPLOYMENT="YOUR-CHAT-DEPLOYMENT"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="YOUR-EMBEDDING-DEPLOYMENT"
```

Create or update the Secret:

```bash
kubectl -n bioops-dev create secret generic bioops-secrets \
  --from-literal=AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
  --from-literal=AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
  --from-literal=AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
  --from-literal=AZURE_OPENAI_CHAT_DEPLOYMENT="$AZURE_OPENAI_CHAT_DEPLOYMENT" \
  --from-literal=AZURE_OPENAI_EMBEDDING_DEPLOYMENT="$AZURE_OPENAI_EMBEDDING_DEPLOYMENT" \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN" \
  --dry-run=client \
  -o yaml \
  | kubectl apply -f -
```

Clear the shell variables:

```bash
unset AZURE_OPENAI_API_KEY GITHUB_TOKEN
```

---

## 10. Browser Basic Auth

The browser authentication Secret is:

```text
bioops-edge-auth
```

Create it:

```bash
BIOOPS_USERNAME="bioops"

read -rsp "Browser password: " BIOOPS_PASSWORD
echo

BIOOPS_PASSWORD_HASH="$(
  docker run --rm caddy:2-alpine \
  caddy hash-password \
  --plaintext "$BIOOPS_PASSWORD"
)"
```

```bash
kubectl -n bioops-dev create secret generic bioops-edge-auth \
  --from-literal=username="$BIOOPS_USERNAME" \
  --from-literal=password-hash="$BIOOPS_PASSWORD_HASH" \
  --dry-run=client \
  -o yaml \
  | kubectl apply -f -
```

```bash
unset BIOOPS_PASSWORD BIOOPS_PASSWORD_HASH
```

---


## 11. Validate Kubernetes and Argo manifests

Render the Kubernetes release:

```bash
kubectl kustomize deploy/k8s \
  > /tmp/bioops-k8s-rendered.yaml
```

Render the Argo resources:

```bash
kubectl kustomize deploy/argo \
  > /tmp/bioops-argo-rendered.yaml
```

Client-side validation:

```bash
kubectl apply -k deploy/k8s \
  --dry-run=client

kubectl apply -k deploy/argo \
  --dry-run=client
```

---

## 12. Deploy Kubernetes resources

```bash
kubectl apply -k deploy/k8s
```

Watch the API rollout:

```bash
kubectl -n bioops-dev rollout status \
  deployment/bioops-api \
  --timeout=5m
```

Inspect resources:

```bash
kubectl -n bioops-dev get pods -o wide
kubectl -n bioops-dev get services
kubectl -n bioops-dev get pvc
kubectl -n bioops-dev get cronjobs
```

The BioOps API Pod should reach:

```text
2/2 Running
```

Check API logs:

```bash
kubectl -n bioops-dev logs \
  deployment/bioops-api \
  -c bioops-api \
  --tail=200
```

---

## 13. Deploy Argo WorkflowTemplates

Argo resources are deployed separately:

```bash
kubectl apply -k deploy/argo
```

Verify:

```bash
kubectl -n bioops-dev get \
  workflowtemplates.argoproj.io
```

Expected templates include:

```text
bioops-knowledge-ingest
bioops-submit-master-local
```

---

## 14. Knowledge ingestion workflow

Submit the knowledge-ingestion workflow:

```bash
argo submit \
  -n bioops-dev \
  deploy/argo/workflow-ci.yaml \
  --watch
```

Inspect:

```bash
argo list -n bioops-dev
argo logs -n bioops-dev @latest
```

Success criteria:

```text
Qdrant is reachable
Knowledge source files are found
Ingestion completes successfully
Workflow phase is Succeeded
Container exit code is 0
```

---

## 15. Submit Master demo

Apply the Submit Master WorkflowTemplate:

```bash
kubectl apply \
  -f deploy/argo/submit-master-template.yaml
```

Submit the demo Workflow:

```bash
argo submit \
  -n bioops-dev \
  --from workflowtemplate/bioops-submit-master-local \
  -p batch_id=batch-demo-001 \
  -p sample_id=sample1 \
  -p attempt=0 \
  -p samples=sample1 \
  -p stage=2 \
  -p mode=demo \
  --watch
```

Inspect:

```bash
argo get -n bioops-dev @latest
argo logs -n bioops-dev @latest
```

The current D5 retry implementation does not restart the same failed Pod.

It:

```text
finds a failed Argo Workflow
checks whether the failure is safely retryable
checks retry limits and active retries
copies the old Workflow specification
creates a new Argo Workflow
allows Argo to create fresh Pods
```

The original failed Workflow and Pods remain available for audit and diagnosis.

SubmitMaster status and retry selection is label-driven. Every sample Workflow
and Pod must carry `bioops.dev/batch-id`, `bioops.dev/sample-id`, and
`bioops.dev/attempt`. Batch D3 reports count only the latest attempt for each
sample and include counts, percentages, current-step distribution, and runtime
statistics. D5 first performs a read-only retry assessment and creates a new
sample Workflow only after `CONFIRM RETRY <workflow-name>` is sent exactly.

---

## 16. Cluster Health CronJob

The Cluster Health schedulers are defined at:

```text
deploy/k8s/cluster-health/cronjob.yaml
deploy/k8s/cluster-health/error-cronjob.yaml
```

They run:

```text
python -m bioops.jobs.cluster_health_monitor --mode status
python -m bioops.jobs.cluster_health_monitor --mode errors
```

Check the CronJob:

```bash
kubectl -n bioops-dev get \
  cronjob bioops-cluster-health-monitor bioops-cluster-error-monitor
```

Run it manually:

```bash
kubectl -n bioops-dev create job \
  --from=cronjob/bioops-cluster-health-monitor \
  cluster-health-monitor-manual-$(date +%s)
```

Inspect logs:

```bash
kubectl -n bioops-dev logs \
  -l component=cluster-health-monitor \
  --tail=200
```

Current limitations:

```text
Reports are written to Job logs and sent to the browser notification inbox.
The full health report runs hourly, including while the pipeline is idle.
Analyzed recent-error alerts run every 30 minutes and stay quiet when healthy.
Both CronJobs are suspended until the new image is built, pushed, and validated.
An in-cluster CronJob cannot detect that its own cluster is powered off.
```

Complete cluster-outage detection requires an external monitor.

---

## 17. Batch Status CronJob

The Batch Status scheduler is defined at:

```text
deploy/k8s/batch-status/cronjob.yaml
```

It updates:

```text
/data/bioops_batch_status.sqlite3
```

Check it:

```bash
kubectl -n bioops-dev get \
  cronjob batch-status-sync
```

Enable it:

```bash
kubectl -n bioops-dev patch \
  cronjob batch-status-sync \
  --type=merge \
  -p '{"spec":{"suspend":false}}'
```

Run it once manually:

```bash
kubectl -n bioops-dev create job \
  --from=cronjob/batch-status-sync \
  batch-status-sync-manual-$(date +%s)
```

Google Sheets synchronization exists in code but is disabled in the current deployment.

---

## 18. Browser interface

Find the public Service:

```bash
kubectl -n bioops-dev get \
  service bioops-api \
  -o wide
```

Check the health endpoint:

```bash
curl -fsS \
  "https://YOUR-BIOOPS-HOST/health"

echo
```

Expected response:

```json
{"status":"ok"}
```

Open the browser interface:

```text
https://bioops.84-201-181-221.sslip.io/
```

Open the live batch-status dashboard:

```text
https://bioops.84-201-181-221.sslip.io/batches
```

---

## 19. Agent acceptance prompts

### General Agent

```text
Hello. What can BioOps help me with?
```

### Knowledge Agent

```text
Explain the BioOps orchestrator using indexed project information.
```

### Review Agent

```text
Review the Mayaro8/BioOps repository and identify the three most important engineering risks.
```

### Cluster Health Agent

```text
Check cluster health and show the active pipeline steps.
```

### Submit Master Agent

```text
Show the Submit Master status for batch batch-demo-001.
```

### Batch Status Agent

```text
Show the latest batch statuses.
```

### Storage Agent

```text
How many objects are in the bucket inventory?
```

---

## 20. Minimum demonstration sequence

1. Show the active Git branch.
2. Show the current image tag.
3. Show Pods, Services, PVCs, and CronJobs in `bioops-dev`.
4. Submit the knowledge-ingestion workflow.
5. Show that the workflow reaches `Succeeded`.
6. Open the BioOps browser interface.
7. Run one prompt for each required agent.
8. Submit the Submit Master demo Workflow.
9. Show the successful Argo execution.
10. Record the demonstration.

---
