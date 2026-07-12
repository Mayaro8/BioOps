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
- active pipeline steps;
- runtime;
- ETA where configured;
- cost where available.

Example:

```text
Check cluster health.
```

The Cluster Health Agent is read-only. It does not restart Pods.

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

Supports Submit Master operations through Argo Workflows.

Epic D consists of:

```text
D1 — generate a Submit Master configuration
D2 — launch Submit Master
D3 — monitor status, progress, errors, logs, runtime, cost, and ETA
D4 — report failed Pods or workflow nodes
D5 — safely retry a failed Workflow
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

The canonical image tag is:

```bash
IMAGE="cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:k8s-demo-llm-routing-20260710"
```

All active Kubernetes and Argo manifests should use the same image.

Check image references:

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
git switch k8s-demo-llm-action-routing
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
IMAGE="cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:k8s-demo-llm-routing-20260710"

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


## 12. Validate Kubernetes and Argo manifests

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

## 13. Deploy Kubernetes resources

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

## 14. Deploy Argo WorkflowTemplates

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

## 15. Knowledge ingestion workflow

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

## 16. Submit Master demo

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
  -p samples=sample1,sample2 \
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

---

## 17. Cluster Health CronJob

The Cluster Health scheduler is defined at:

```text
deploy/k8s/cluster-health/cronjob.yaml
```

It runs:

```text
python -m bioops.jobs.cluster_health_monitor
```

Check the CronJob:

```bash
kubectl -n bioops-dev get \
  cronjob cluster-health-monitor
```

Run it manually:

```bash
kubectl -n bioops-dev create job \
  --from=cronjob/cluster-health-monitor \
  cluster-health-monitor-manual-$(date +%s)
```

Inspect logs:

```bash
kubectl -n bioops-dev logs \
  -l app.kubernetes.io/name=cluster-health-monitor \
  --tail=200
```

Current limitations:

```text
The periodic report is written to Job logs.
Browser notifications are not yet implemented.
An in-cluster CronJob cannot detect that its own cluster is powered off.
```

Complete cluster-outage detection requires an external monitor.

---

## 18. Batch Status CronJob

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

## 19. Browser interface

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

---

## 20. Agent acceptance prompts

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
Check cluster health.
```

### Submit Master Agent

```text
Show the current Submit Master workflow progress.
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

## 21. Minimum demonstration sequence

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

