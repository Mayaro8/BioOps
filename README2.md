# BioOps: Complete Implementation and Operations Guide

This document describes the executable implementation on the public
`ifra-final` branch at commit `76a21ce`. It distinguishes implemented behavior
from demonstrations, mock integrations, suspended monitors, and planned work.

BioOps is a Python multi-agent assistant for bioinformatics operations. It
combines browser chat, Azure OpenAI routing, deterministic tools, Kubernetes
and Argo inspection, persistent status databases, storage inventory analysis,
code review, and proactive infrastructure monitoring.

Public endpoint:

```text
https://bioops.84-201-181-221.sslip.io/
```

## 1. Architecture

### Reactive request path

```text
Browser or CLI
    |
    v
FastAPI /chat or bioops.main
    |
    v
LangGraph orchestrator
    |
    v
Azure OpenAI top-level router
    |
    +-- General Agent
    +-- Knowledge Agent -------> Azure embeddings + Qdrant
    +-- Cluster Health Agent --> Kubernetes Pods and logs
    +-- Review Agent ----------> local Git or GitHub API
    +-- Submit Master Agent ---> Argo Workflow CRDs and Pods
    +-- Batch Status Agent ----> SQLite snapshot database
    +-- Storage Agent ---------> bucket inventory CSV
    +-- Infra & Cost Agent ----> VM inventory
```

### Proactive monitoring path

```text
Kubernetes CronJob
    |
    v
Deterministic monitor
    |
    +-- Kubernetes health
    +-- VM cost/GPU checks
    +-- database health
    +-- queue drainage
    +-- Cloud Functions health
    +-- batch status synchronization
    |
    v
BrowserAlertClient or AlertTool
    |
    v
POST /internal/alerts
    |
    v
SQLite notification inbox
    |
    v
Browser notification panel
```

Reactive agents answer user requests immediately. Proactive jobs run on
schedules without a chat request.

All current monitoring CronJobs are committed with `suspend: true`. They must
be manually tested before scheduling is enabled.

## 2. Repository structure

```text
BioOps/
├── configs/
│   └── agents.yaml
├── data/
├── deploy/
│   ├── argo/
│   └── k8s/
├── docs/
├── src/bioops/
│   ├── agents/
│   ├── api/
│   ├── jobs/
│   ├── rag/
│   ├── tools/
│   ├── graph_orchestrator.py
│   └── main.py
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

`deploy/k8s/` is the canonical Kubernetes release tree. The older `k8s/`
directory contains legacy or demonstration manifests and should not be treated
as the primary deployment source.

## 3. Browser, API, and notifications

The Kubernetes Deployment starts:

```text
python -m uvicorn bioops.api.bitrix_app:app --host 0.0.0.0 --port 8000
```

Despite the legacy module name, `bitrix_app.py` contains the canonical browser
application.

### API endpoints

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/` | Returns the browser chat page. |
| `POST` | `/chat` | Validates a non-empty message and runs the LangGraph orchestrator. |
| `GET` | `/health` | Returns API health information. |
| `POST` | `/internal/alerts` | Stores a monitor notification. |
| `GET` | `/alerts` | Returns recent notifications and unread count. |
| `POST` | `/alerts/{id}/read` | Marks a notification as read. |
| `POST` | `/bitrix/message` | Legacy optional Bitrix adapter. |

If `BIOOPS_INTERNAL_ALERT_TOKEN` is configured, `/internal/alerts` requires the
same value in the `X-BioOps-Alert-Token` header.

The browser polls `/alerts` every 15 seconds. The notification panel:

- is collapsible;
- displays severity and timestamp;
- counts unread notifications;
- shows the ten newest notifications by default;
- allows individual notifications to be marked as read.

Notifications are stored in:

```text
/data/bioops_notifications.sqlite3
```

The notification table contains an ID, title, message, severity, UTC creation
timestamp, and read flag.

The API currently mounts the Batch Status PVC at `/data`, so Batch Status data,
exports, and browser notifications share the same persistent volume.

## 4. LangGraph and LLM routing

`src/bioops/graph_orchestrator.py` builds a LangGraph containing:

- one router node;
- one node for every enabled agent;
- a routing-error node;
- an edge from each selected agent to the graph end.

Agent enablement comes from `configs/agents.yaml`. The General Agent is
mandatory even if configuration attempts to disable it.

### Top-level router

`LLMRouterTool` asks Azure OpenAI to return strict JSON naming exactly one
enabled agent.

There is no keyword fallback. BioOps returns a visible `routing_error` when:

- Azure OpenAI is not configured;
- the router request fails;
- the model returns invalid JSON;
- the model selects an unsupported agent;
- the model selects a disabled agent.

### Second-stage routing

Several agents use an additional structured LLM layer:

- Submit Master selects batch, sample, workflow, failure, retry, UI, latest, or
  help actions.
- Batch Status selects batch, latest, failed, running, completed, stale,
  export-information, or sync-information actions.
- Storage selects summary, count, size, class, file-list, structure, or
  extension-breakdown actions.
- Knowledge rewrites the retrieval query.
- Review parses the requested review mode and performs patch analysis.

`LLMActionRouter` validates the action and parameter names against fixed
schemas. Unsupported actions or parameters fail closed.

The LLM selects intent. Deterministic code performs Kubernetes reads,
calculations, database access, file filtering, and confirmed workflow changes.

Required Azure variables:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_VERSION
AZURE_OPENAI_CHAT_DEPLOYMENT
AZURE_OPENAI_EMBEDDING_DEPLOYMENT
```

## 5. Agents

### 5.1 General Agent

The General Agent handles greetings, unclear questions, unsupported requests,
and general BioOps conversation.

It uses Azure OpenAI directly and is instructed not to claim that it inspected
Kubernetes, GitHub, storage, or cloud systems unless a specialist tool ran.

If Azure OpenAI is unavailable, it returns a configuration explanation instead
of inventing an answer.

It has no operational side effects.

Example:

```text
Hello. What can BioOps help me with?
```

### 5.2 Knowledge Agent

The Knowledge Agent implements retrieval-augmented generation over BioOps
documentation.

Request flow:

1. Rewrite the question using an LLM-only query rewriter.
2. Embed the rewritten query using Azure OpenAI.
3. Retrieve the five nearest Qdrant chunks using cosine distance.
4. Pass the original question and retrieved chunks to the chat model.
5. Answer only from the supplied context.
6. Include a short Sources section.

The ingestion pipeline recursively reads files under `docs/` with these
extensions:

```text
.md
.txt
.yaml
.yml
.pdf
```

It splits text into sentence-like units, creates approximately 900-character
chunks with one-unit overlap, embeds the chunks, and inserts them into Qdrant.

Ingestion calls `recreate_collection`, so it replaces the old collection before
inserting the new vectors.

Qdrant defaults:

```text
Local URL:       http://localhost:6333
Kubernetes URL:  http://qdrant:6333
Collection:      bioops_knowledge
```

Example:

```text
Explain the BioOps orchestrator using indexed project documentation.
```

### 5.3 Cluster Health Agent

The Cluster Health Agent is a live, read-only Kubernetes inspector.

It loads in-cluster credentials inside Kubernetes and falls back to local
kubeconfig outside the cluster.

For every Pod it reads:

- Pod name;
- namespace;
- phase;
- assigned worker node;
- `pipeline_step` label;
- start time;
- runtime in minutes.

The report separates:

- infrastructure Pods beginning with `bioops-api` or `qdrant`;
- running pipeline Pods carrying `pipeline_step`;
- other running Pods without `pipeline_step`.

It reports:

- overall health;
- infrastructure status;
- active pipeline steps;
- recent errors;
- configured cost;
- configured ETA.

The public `ifra-final` source currently lists active pipeline Pods
individually.

Grouped Cluster Health counts and percentages, average runtime, quartiles,
shortest runtime, and longest runtime were part of the improvement work, but
that code is not present in the current public `ifra-final` source. It must be
merged before those features are claimed as active in this branch.

#### Recent errors

Recent error discovery is deterministic and currently keyword-based.

It:

- checks waiting containers;
- checks non-zero terminated containers;
- reads init-container and application-container logs;
- ignores successfully completed historical Jobs;
- searches recent logs for OOM, traceback, exception, error, failure, RBAC,
  timeout, and connection terms;
- returns at most three unique errors by default;
- checks the previous 60 minutes by default;
- reads 50 log lines by default.

#### Cost

The current cost mode is `local_free`. It reports zero configured-currency cost
and explicitly states that no cloud billing API was queried.

#### ETA

Configured expected durations are:

```text
bam-to-gvcf: 120 minutes
gvcf-to-vcf: 45 minutes
transfer-bam: 10 minutes
transfer-vcf: 10 minutes
```

Remaining ETA is expected duration minus current Pod runtime, bounded at zero.

The Cluster Health Agent never restarts or deletes Pods.

Example:

```text
Check cluster health.
```

### 5.4 Review Agent

The Review Agent supports:

- local repository review;
- GitHub repository overview;
- open pull-request listing;
- review of one pull request;
- branch comparison.

An LLM-only parser extracts:

- review mode;
- repository;
- PR number;
- base branch;
- head branch;
- local path.

#### GitHub review

GitHub mode uses PyGithub.

Repository overview checks for:

- README;
- `src/bioops`;
- tests;
- Dockerfile;
- Docker Compose;
- requirements;
- GitHub Actions;
- committed caches;
- committed `.env`.

PR and branch-comparison reports include:

- changed-file count;
- additions and deletions;
- bounded patch excerpts;
- deterministic issues and risks;
- mandatory Azure OpenAI patch review.

#### Local review

Local mode uses read-only Git commands. It:

- lists changed and tracked files;
- detects test files;
- flags caches, credential-like files, and very large files;
- runs `py_compile` on up to 100 Python files.

The Review Agent never comments, approves, rejects, closes, merges, or modifies
GitHub content. It does not modify local repository files.

GitHub access uses:

```text
GITHUB_TOKEN
```

Example:

```text
Review repo=Mayaro8/BioOps base=main head=ifra-final.
```

### 5.5 Submit Master Agent

The Submit Master Agent monitors sample-scoped Argo workflows and performs
confirmed targeted retries.

The included WorkflowTemplate demonstrates the expected labels, parameters,
task chaining, monitoring, and retry behavior. It is not the full production
SNP pipeline package.

#### Workflow and Pod identity

Expected labels:

```text
bioops.dev/workload=submit-master
bioops.dev/batch-id=<batch>
bioops.dev/sample-id=<sample>
bioops.dev/attempt=<attempt-number>
```

Argo also places this label on Workflow Pods:

```text
workflows.argoproj.io/workflow=<workflow-name>
```

The agent uses these labels instead of selecting an arbitrary latest Pod.

#### Pagination and scale

Workflow reads use label selectors and continuation-token pagination.

Defaults:

```text
Workflow page size: 100
Pod page size:      200
Maximum details:    10
```

Pages are accumulated until Kubernetes returns no continuation token.

#### Batch status

For a batch, Workflow attempts are sorted newest first. Only the latest attempt
for each sample is included in the current sample state.

The report includes:

- distinct sample count;
- total Workflow-attempt count;
- Workflow-phase counts and percentages;
- current-step counts and percentages;
- average runtime;
- first quartile;
- median;
- third quartile;
- shortest-running sample;
- longest-running sample;
- failed sample count;
- bounded failed-sample list.

The test suite includes a 1,000-sample aggregation test.

#### Sample status

For one sample, the agent reports:

- batch ID;
- sample ID;
- Workflow name;
- attempt;
- phase;
- current step;
- runtime;
- Pod groups by pipeline step and phase;
- Pod counts and percentages.

If a sample ID exists in multiple batches, the agent refuses to guess and
requires an explicit `batch_id`.

Recognized steps include:

```text
config-creator
submit-master
haplotypecaller
gvcf-to-vcf
beagle
transfer-vcf
transfer-bam
```

#### D1 and D2

The demonstration DAG is:

```text
config-creator -> submit-master
```

Config Creator accepts:

```text
batch_id
sample_id
attempt
samples
stage
mode
```

It writes JSON to `/tmp/submit-master-config.json` and exposes it as an Argo
output parameter.

Submit Master receives that JSON through `SUBMIT_MASTER_CONFIG`, verifies all
required fields, and runs the demonstration.

The `launch_ui` action starts a `kubectl port-forward` process and attempts to
open the Argo UI. It does not directly submit a Workflow.

Workflow submission happens through the Argo UI, Argo CLI, or Kubernetes API.

#### D3 monitoring

D3 supports:

- explicit batch status;
- explicit sample status;
- explicit Workflow status;
- latest Workflow only when the user explicitly requests latest.

The standalone D3 script requires one of:

```text
--batch-id
--sample-id
--workflow-name
--latest
```

#### D4 failure reporting

D4 requires an explicit Workflow or a sample that resolves to one Workflow.

It:

- reads failed and error Argo nodes;
- resolves candidate Pod names;
- reads bounded Pod logs;
- reports up to five failed nodes;
- applies deterministic diagnosis patterns to messages and logs.

#### D5 targeted retry

A retry request first performs a read-only assessment.

A Workflow mutation occurs only after the exact message:

```text
CONFIRM RETRY <workflow-name>
```

Potentially retryable categories include:

- node loss;
- Pod eviction;
- temporary resource pressure;
- timeouts;
- temporary service errors;
- transient network failures;
- API rate limits.

Blocked categories include:

- missing programs;
- missing Python modules;
- RBAC failures;
- image-pull failures;
- invalid input or configuration;
- missing files;
- authentication failures;
- permission failures;
- unknown failure reasons.

Before creating a retry, D5 checks:

- the Workflow is `Failed` or `Error`;
- the failure matches a safe retry rule;
- no retry for the same root Workflow is currently active;
- the configured retry maximum, currently two, is not reached.

A permitted retry:

- copies the old Workflow specification;
- removes a copied `shutdown` instruction;
- increments the `attempt` parameter;
- preserves batch and sample labels;
- adds root, parent, and retry annotations;
- creates a DNS-safe Workflow name;
- leaves the old failed Workflow and Pods available for audit.

Examples:

```text
Show Submit Master status for batch B104.
Show sample S927 in batch B104.
Diagnose workflow bioops-submit-master-s927.
Retry workflow bioops-submit-master-s927.
CONFIRM RETRY bioops-submit-master-s927
```

### 5.6 Batch Status Agent

The Batch Status Agent is a persisted, read-only reporting layer.

It is different from Submit Master monitoring:

- Submit Master reads current Argo Workflows and Pods live.
- Batch Status reads previously synchronized SQLite snapshots.

The synchronization job converts matching Argo Workflows into rows containing:

```text
batch_id
workflow_name
workflow_template
stage
mode
sample_ids
status
progress
current_step
created_at
started_at
finished_at
last_checked_at
error_message
argo_url
```

The primary key is `workflow_name`. The table also has indexes for batch ID and
status.

Database and exports:

```text
/data/bioops_batch_status.sqlite3
/data/batch_status.csv
/data/batch_status.json
```

Chat actions support:

- one explicit batch;
- latest records;
- failed/error records;
- running/pending records;
- completed records;
- stale records;
- export instructions;
- synchronization instructions.

Stale means an active row's `last_checked_at` is older than the configured
30-minute threshold.

Chat deliberately does not start synchronization, export, or Kubernetes Jobs.

Google Sheets one-way upsert code exists and uses Workflow name as its identity.
It can create or correct the header row.

Google Sheets is currently disabled, and the deployed CronJob passes
`--no-sheet`.

Current limitations:

- only 100 Workflows are processed by the deployed sync;
- the Batch Status Argo scanner lacks continuation-token pagination;
- Workflow attempts remain separate database rows;
- a specific-batch chat answer shows at most five detailed rows;
- old Workflow rows are not removed;
- Google Sheets is disabled;
- the CronJob is suspended.

Example:

```text
What is the persisted status of batch B104?
```

### 5.7 Storage / Bucket Agent

The Storage Agent answers read-only questions from a CSV inventory snapshot.

It does not scan the complete bucket for every chat request.

Supported actions:

- summary;
- object count;
- total size;
- storage-class totals;
- bounded file listing;
- top-level prefix structure;
- file-extension breakdown.

Filters include:

- exact prefix;
- generic extension;
- configured filename suffix;
- storage class;
- output limit.

Known suffixes include:

```text
beagle.imputation.vcf.gz
imputation.vcf.gz
```

Prefix matching respects path boundaries, so `batch-1` does not accidentally
match `batch-10`.

Supported inventory formats:

- BioOps header CSV with key, size, modification time, storage class, and
  inventory date;
- company headerless CSV with bucket, key, size, and storage class;
- one CSV file;
- a directory of dated snapshots.

When a directory is configured, the agent selects the newest inventory using:

1. embedded inventory date;
2. date in filename;
3. filesystem modification time.

Every answer reports the inventory file and date.

The manual boto3 exporter:

- uses paginated `list_objects_v2`;
- reads an S3-compatible bucket;
- writes to a temporary CSV;
- atomically replaces the target inventory.

No enabled bucket-inventory refresh CronJob is included in canonical
`deploy/k8s`.

Example:

```text
How many imputation.vcf.gz files are under results/B104?
```

### 5.8 Infra & Cost Agent

The interactive Infra Agent currently exposes E1 Compute VM checks.

E2-E4 exist as separate proactive jobs.

#### E1 Compute VMs

A VM alerts only when:

1. it is running;
2. runtime is more than three hours;
3. projected monthly cost exceeds 50,000 RUB or the VM has a GPU.

The provider interface is extensible, but only `MockComputeProvider` is
implemented. It reads:

```text
tests/fixtures/mock_compute_vms.json
```

No real Yandex Compute provider is currently implemented.

#### E2 database health

The database monitor reads mock MongoDB, MySQL, and ClickHouse records.

It reports:

- unreachable hosts;
- CPU above 85%;
- RAM above 90%;
- unfinished ClickHouse mutations older than 30 minutes.

Unreachable hosts make the report critical. Threshold and mutation findings are
warnings.

#### E3 queue drainage

For non-empty mock queues, it reports:

- oldest message above 900 seconds;
- output below one message per minute;
- estimated drain time above 60 minutes.

#### E4 Cloud Functions

It reports:

- error rate above 5%;
- load above three times baseline;
- any critical log errors.

Error-rate and critical-log findings are critical. Load-only findings are
warnings.

All E1-E4 CronJobs are suspended.

E2-E4 send healthy as well as unhealthy reports to the browser inbox.

The local `configs/agents.yaml` enables `infra_cost`, but
`deploy/k8s/config/agents.yaml` currently omits that section. Therefore the
interactive Infra Agent is not enabled by the live Kubernetes router even
though the standalone monitoring CronJobs exist.

## 6. Reactive actions and side effects

| Operation | Trigger | Side effect |
|---|---|---|
| General, Knowledge, Cluster Health, Review, Batch Status, Storage, E1 report | Browser or CLI | Read-only except for external LLM/API calls. |
| Submit Master status and D4 | Browser or CLI | Read-only Kubernetes/Argo access. |
| Submit Master UI | Explicit request | Starts port-forward and tries to open a browser. |
| D5 assessment | Retry request | Read-only assessment. |
| D5 confirmation | Exact confirmation | Creates one new Argo Workflow if checks pass. |
| Knowledge ingestion | Manual Job/Workflow | Recreates and repopulates Qdrant. |
| Batch synchronization | Manual/scheduled job | Upserts SQLite and optionally Google Sheets. |
| Batch export | Manual/scheduled job | Writes CSV and JSON. |
| Bucket export | Manual job | Reads S3 listing and replaces inventory CSV. |
| Internal alert | Monitor HTTP request | Inserts notification SQLite row. |
| Mark alert read | Browser action | Updates notification SQLite row. |

Review, Storage, Cluster Health, and normal Submit Master monitoring do not
modify their external sources.

The only Workflow mutation exposed through chat is the confirmed D5
resubmission.

## 7. Proactive jobs

| Job | Manifest | Schedule | State | Data source | Output |
|---|---|---:|---|---|---|
| Cluster Health | `deploy/k8s/cluster-health/cronjob.yaml` | every 15 min | suspended | Kubernetes Pods/logs | Browser |
| Batch sync/export | `deploy/k8s/batch-status/cronjob.yaml` | every 30 min | suspended | Argo Workflows | SQLite/CSV/JSON |
| E1 VM cost/GPU | `deploy/k8s/infra-cost/cronjob.yaml` | every 15 min | suspended | Mock VM JSON | Browser |
| E2 database | `database-health-cronjob.yaml` | every 15 min | suspended | Mock DB JSON | Browser |
| E3 queue | `queue-health-cronjob.yaml` | every 10 min | suspended | Mock queue JSON | Browser |
| E4 functions | `function-health-cronjob.yaml` | every 10 min | suspended | Mock function JSON | Browser |

The Cluster Health job:

- sends a warning when recent errors exist;
- sends status while labeled pipeline Pods are active;
- sends nothing while idle and error-free.

Its manifest currently points to:

```text
http://bioops-api:8000/internal/alerts
```

After the Caddy Kustomize patch, the public `bioops-api` Service exposes ports
80 and 443, not 8000.

Before enabling Cluster Health, change the URL to the existing internal Service:

```text
http://bioops-api-internal:8000/internal/alerts
```

An in-cluster CronJob cannot report a complete cluster shutdown because it
stops with the cluster. Complete outage detection requires an external monitor.

## 8. Docker image and Docker Compose

### Dockerfile

The image is based on:

```text
python:3.12-slim
```

It installs:

- Git;
- curl;
- CA certificates;
- Python dependencies;
- project source;
- current stable `kubectl`.

The default command is:

```text
python -m bioops.main
```

### Docker Compose services

`qdrant`:

- uses `qdrant/qdrant:latest`;
- exposes ports 6333 and 6334;
- persists data in `qdrant_storage`.

`bioops`:

- builds the repository Dockerfile;
- loads `.env`;
- mounts the repository at `/app`;
- mounts kubeconfig read-only;
- uses host networking;
- runs interactively.

Because BioOps uses host networking, `QDRANT_URL=http://localhost:6333`
reaches Qdrant through its host-published port.

### Local workflow

```bash
cp .env.example .env
# Fill the required values in .env.

docker compose build bioops
docker compose up -d qdrant

docker compose run --rm bioops \
  python -m bioops.rag.ingest

docker compose run --rm bioops \
  python -m pytest -q

docker compose run --rm bioops \
  python -m bioops.main
```

Run one question:

```bash
docker compose run --rm bioops \
  python -m bioops.main ask "Check cluster health"
```

Run FastAPI locally:

```bash
docker compose run --rm bioops \
  python -m uvicorn bioops.api.bitrix_app:app \
  --host 0.0.0.0 --port 8000
```

### Build and push

```bash
yc container registry configure-docker

TAG="bioops-$(date +%Y%m%d-%H%M%S)"
IMAGE="cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops:${TAG}"

docker build -t "$IMAGE" .
docker push "$IMAGE"
```

Pushing stores an image in the registry. Kubernetes does not use it until the
Deployment or manifest is updated and applied.

## 9. Kubernetes deployment

### Public traffic

The `bioops-api` Deployment has one Pod containing:

- `bioops-api`, running Uvicorn on port 8000;
- `caddy`, listening on ports 80 and 443.

The Kustomize patch changes the public Service to a `LoadBalancer` on ports 80
and 443.

Caddy:

- terminates TLS;
- exposes `/health` without Basic Auth;
- requires Basic Auth for other routes;
- reverse-proxies to Uvicorn through `127.0.0.1:8000`;
- adds HSTS, content-type, frame, and referrer security headers;
- removes the Server header.

`bioops-api-internal` is a ClusterIP Service exposing Uvicorn on port 8000 for
in-cluster monitors.

### Persistent state

| PVC | Size | Consumer | Contents |
|---|---:|---|---|
| `qdrant-data` | 5 GiB | Qdrant | Vector collection |
| `bioops-batch-status-db` | 1 GiB | API and Batch Status | Batch DB, exports, notification DB |
| `bioops-caddy-data` | 1 GiB | Caddy | TLS and Caddy state |

Qdrant is internal-only through a ClusterIP Service on ports 6333 and 6334.

Its StatefulSet has one replica and currently uses the unpinned
`qdrant/qdrant:latest` image.

### ConfigMaps

Kustomize generates:

- `bioops-config` from `runtime.env`;
- `bioops-agents-config` from Kubernetes `agents.yaml`;
- `bioops-bucket-inventory` from the demo CSV;
- `bioops-infra-mocks` from E2-E4 JSON fixtures;
- `bioops-caddy-config` from the Caddyfile.

### Secrets

Secrets are not committed.

The Deployment expects:

- `bioops-secrets` for Azure OpenAI, GitHub, optional alert token, and optional
  legacy integrations;
- `bioops-edge-auth` containing `username` and Caddy `password-hash`.

### Scheduling

Workloads use:

```text
Namespace:       bioops-dev
ServiceAccount:  bioops-student
Node selector:   genoteknodetype=fastmri-cpu
Toleration:      yandex.cloud/preemptible=true
```

The API requests 250 millicores and 512 MiB and is limited to one CPU and 2
GiB.

### RBAC status

The repository contains RBAC manifests, but the canonical root Kustomization
does not include:

```text
deploy/k8s/cluster-health/rbac.yaml
deploy/k8s/rbac/bioops-executor.yaml
```

The executor manifest creates `bioops-executor`, while active workloads use
`bioops-student`.

The required Pod/log and Argo Workflow permissions must already exist or be
applied by a cluster administrator.

D5 requires permission to create Argo Workflow resources.

### Image pins

The release currently uses different tested image tags:

| Component | Image |
|---|---|
| API and Submit Master demo | `submit-master-20260715-192759` |
| Cluster Health | `infra-final-cluster-health-20260714-115127` |
| Infra E1-E4 | `infra-final-periodic-e1-e4-20260713` |
| Batch Status and Knowledge ingestion | `k8s-demo-llm-routing-20260710` |
| Caddy | `caddy:2-alpine` |
| Qdrant | `qdrant/qdrant:latest` |

### Render and deploy

```bash
kubectl kustomize deploy/k8s \
  > /tmp/bioops-k8s-rendered.yaml

kubectl apply -k deploy/k8s \
  --dry-run=client

kubectl apply -k deploy/k8s

kubectl -n bioops-dev rollout status \
  deployment/bioops-api \
  --timeout=5m
```

Inspect:

```bash
kubectl -n bioops-dev get pods -o wide
kubectl -n bioops-dev get services
kubectl -n bioops-dev get pvc
kubectl -n bioops-dev get cronjobs
```

Check configured images:

```bash
kubectl -n bioops-dev get deployment bioops-api \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{" -> "}{.image}{"\n"}{end}'
```

Check actually pulled images and digests:

```bash
kubectl -n bioops-dev get pods -l app=bioops-api \
  -o jsonpath='{range .items[*]}{"Pod: "}{.metadata.name}{"\n"}{range .status.containerStatuses[*]}{"  "}{.name}{" -> "}{.image}{"\n  Digest: "}{.imageID}{"\n"}{end}{end}'
```

## 10. Argo workflows

Apply Argo resources separately:

```bash
kubectl apply -k deploy/argo
```

The Argo Kustomization contains:

- `bioops-knowledge-ingest`;
- `bioops-submit-master-local`.

Run knowledge ingestion:

```bash
argo submit -n bioops-dev \
  deploy/argo/workflow-ci.yaml \
  --watch
```

Run one Submit Master sample:

```bash
argo submit -n bioops-dev \
  --from workflowtemplate/bioops-submit-master-local \
  -p batch_id=B104 \
  -p sample_id=S927 \
  -p attempt=0 \
  -p samples=S927 \
  -p stage=2 \
  -p mode=demo \
  --watch
```

The intended large-batch model is one labeled sample Workflow per sample.

A batch can contain hundreds or approximately 1,000 independent sample
Workflows. Kubernetes schedules their Pods across available workers. BioOps
aggregates them through batch and sample labels rather than assuming the whole
batch advances at the same rate.

## 11. Operating scheduled monitors

List CronJobs:

```bash
kubectl -n bioops-dev get cronjobs
```

Run a suspended CronJob manually:

```bash
JOB="cluster-health-manual-$(date +%s)"

kubectl -n bioops-dev create job \
  --from=cronjob/bioops-cluster-health-monitor \
  "$JOB"

kubectl -n bioops-dev logs "job/$JOB"
```

Enable only after manual validation:

```bash
kubectl -n bioops-dev patch \
  cronjob bioops-cluster-health-monitor \
  --type=merge \
  -p '{"spec":{"suspend":false}}'
```

Disable:

```bash
kubectl -n bioops-dev patch \
  cronjob bioops-cluster-health-monitor \
  --type=merge \
  -p '{"spec":{"suspend":true}}'
```

The same pattern applies to:

```text
batch-status-sync
bioops-infra-cost-monitor
bioops-database-health-monitor
bioops-queue-health-monitor
bioops-function-health-monitor
```

## 12. Configuration

Local configuration:

```text
configs/agents.yaml
```

Kubernetes configuration:

```text
deploy/k8s/config/agents.yaml
```

Keep them synchronized intentionally.

The local Cluster Health namespace is currently `bioops`, while Kubernetes uses
`bioops-dev`.

Important settings:

| Area | Settings |
|---|---|
| Agent enablement | `agents.<name>.enabled` |
| Cluster | namespace, timeout, log tail, error window, ETA |
| Submit Master | Argo namespace/template, labels, pagination, list limit |
| D5 | `d5_max_retries` |
| Batch Status | DB path, stale threshold, Sheet configuration |
| Storage | bucket, inventory path/date, list limit, known suffixes |
| E1 | cost and runtime thresholds |

Most timestamps are still stored and calculated in UTC.

The browser formats notification timestamps using the browser locale.

Moscow time conversion is not consistently implemented in the public source.

## 13. Security and safety

- HTTPS terminates at Caddy.
- `/health` is public.
- Other public routes require Basic Auth.
- Kubernetes Secrets are not committed.
- The internal alert endpoint optionally validates a shared token.
- LLM routing fails closed.
- Review and Storage are read-only.
- Cluster Health is read-only.
- Batch Status chat cannot start synchronization or export.
- D4 and D5 require explicit identifiers.
- D5 requires exact confirmation.
- D5 preserves the failed Workflow.
- CronJobs are suspended by default.

The public branch still contains Bitrix classes, a Bitrix endpoint, and
Bitrix-named D3-D5 scripts.

The browser is canonical, but Bitrix cleanup is not complete.

## 14. Tests

The public branch contains 27 test modules and 107 test functions.

Coverage includes:

- top-level routing;
- second-stage action validation;
- browser API;
- notification persistence;
- Knowledge query rewriting;
- Kubernetes configuration and logs;
- recent error detection;
- proactive Cluster Health behavior;
- Submit Master grouping and 1,000-sample aggregation;
- sample Pod status;
- D5 retry identity and safety;
- Batch Status routing;
- storage parsing and inventory filtering;
- bucket export;
- GitHub review contexts;
- E1-E4 monitor rules.

Run:

```bash
python3 -m pytest -q
```

Or inside Docker:

```bash
docker compose run --rm bioops \
  python -m pytest -q
```

Validate manifests:

```bash
kubectl apply -k deploy/k8s --dry-run=client
kubectl apply -k deploy/argo --dry-run=client
```

## 15. Current limitations

1. Public Cluster Health source does not contain the final grouped
   counts/percentages and runtime quartiles.
2. Cluster error discovery remains keyword-based.
3. Cluster Health alert URL must use the internal API Service.
4. All proactive CronJobs are suspended.
5. Batch Status processes only 100 Workflows and lacks Argo pagination.
6. Batch Status persists attempts rather than latest sample state.
7. Google Sheets synchronization is disabled.
8. E1-E4 use mock inputs rather than live infrastructure providers.
9. Interactive Infra is omitted from deployed agent configuration.
10. E2-E4 send healthy notifications and may create noise.
11. Component image tags are inconsistent.
12. Qdrant uses an unpinned image.
13. Canonical Kustomize does not apply the included RBAC manifests.
14. Internal timestamps are predominantly UTC.
15. Bitrix compatibility code remains.
16. D1-D2 use a demonstration template, not the production SNP package.
17. Complete cluster outage requires an external monitor.

## 16. Demonstration prompts

```text
Hello. What can BioOps help me with?

Explain the BioOps orchestrator using indexed project documentation.

Check cluster health.

Review repo=Mayaro8/BioOps base=main head=ifra-final.

Show Submit Master status for batch B104.

Show sample S927 in batch B104.

Diagnose workflow bioops-submit-master-s927.

What is the persisted status of batch B104?

How many imputation.vcf.gz objects are under results/B104?

Check infrastructure cost risks.
```

## 17. Current release summary

The current release provides:

- browser-based multi-agent chat;
- LLM-only top-level routing;
- structured second-stage action routing;
- Qdrant-backed knowledge retrieval;
- live Kubernetes inspection;
- live Argo inspection;
- scalable Submit Master batch and sample aggregation;
- confirmed targeted sample retry;
- persisted batch status;
- browser notification persistence;
- storage-inventory analytics;
- read-only GitHub and local review;
- mock-backed proactive infrastructure monitoring;
- Docker Compose development;
- Kubernetes and Argo deployment manifests.

It is not yet a fully production-integrated operations platform.

The most important remaining work is to merge final Cluster Health aggregation,
remove Batch Status scale limits, connect real infrastructure providers,
validate and enable schedules, align RBAC and image versions, complete
browser-only cleanup, and make time presentation consistent.
