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
   +-- Knowledge Agent -------> Yandex Wiki index, then bundled docs index in Qdrant
   +-- Cluster Health Agent --> Argo workflow Pods and Pod logs
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

Answers from indexed Yandex Wiki pages first. When Wiki has no relevant result
or its collection is unavailable, it falls back to bundled project documentation
stored in Qdrant.

Example:

```text
Explain the BioOps orchestrator.
```

### Cluster Health Agent

Reads live Kubernetes data for Argo workflow Pods and worker nodes and reports:

- batch-level workflow and Pod counts and percentages;
- container readiness;
- restarts;
- recent workflow Pod errors;
- active pipeline steps aggregated by batch;
- Pod runtime, ETA, and configured cost aggregated by batch;
- node readiness, pressure, resource usage, Pod capacity, and scheduling blockers.

Example:

```text
Show workflow health and its Pods.
```

The Cluster Health Agent uses a second LLM routing layer to choose a bounded
read-only report. It excludes BioOps infrastructure Pods and groups Argo Pods
using `workflows.argoproj.io/workflow`. A 30-minute monitor sends analyzed
workflow Pod errors to the browser, and an hourly monitor sends the full
workflow health report. Conversational reports are read-only; the separate init
watchdog can delete a stuck initialization attempt under its five-retry policy.

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

It should contain the required Azure OpenAI, GitHub, Yandex Wiki, and Yandex
Identity Hub OIDC values.

Example:

```bash
read -rsp "Azure OpenAI API key: " AZURE_OPENAI_API_KEY
echo

read -rsp "GitHub token: " GITHUB_TOKEN
echo

read -rsp "Yandex Wiki read-only OAuth token: " YANDEX_WIKI_TOKEN
echo

read -rp "Identity Hub OpenID Configuration URL: " YANDEX_SSO_OPENID_CONFIGURATION_URL
read -rp "Identity Hub client ID: " YANDEX_SSO_CLIENT_ID
read -rsp "Identity Hub client secret: " YANDEX_SSO_CLIENT_SECRET
echo

BIOOPS_SESSION_SECRET="$(openssl rand -base64 48)"

read -rsp "Developer access code (minimum 5 characters): " BIOOPS_LOCAL_ACCESS_CODE
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
  --from-literal=YANDEX_WIKI_TOKEN="$YANDEX_WIKI_TOKEN" \
  --from-literal=YANDEX_SSO_OPENID_CONFIGURATION_URL="$YANDEX_SSO_OPENID_CONFIGURATION_URL" \
  --from-literal=YANDEX_SSO_CLIENT_ID="$YANDEX_SSO_CLIENT_ID" \
  --from-literal=YANDEX_SSO_CLIENT_SECRET="$YANDEX_SSO_CLIENT_SECRET" \
  --from-literal=BIOOPS_SESSION_SECRET="$BIOOPS_SESSION_SECRET" \
  --from-literal=BIOOPS_LOCAL_ACCESS_CODE="$BIOOPS_LOCAL_ACCESS_CODE" \
  --dry-run=client \
  -o yaml \
  | kubectl apply -f -
```

Clear the shell variables:

```bash
unset AZURE_OPENAI_API_KEY GITHUB_TOKEN YANDEX_WIKI_TOKEN
unset YANDEX_SSO_OPENID_CONFIGURATION_URL YANDEX_SSO_CLIENT_ID
unset YANDEX_SSO_CLIENT_SECRET BIOOPS_SESSION_SECRET
unset BIOOPS_LOCAL_ACCESS_CODE
```

---

## 10. Corporate SSO with Yandex Identity Hub

BioOps uses an Identity Hub OIDC application and never requests the `phone`
scope. For an email-and-password demo without Yandex ID or phone-number login,
create these resources in an Identity Hub organization you control:

1. Create a **user pool** and choose its default login domain.
2. Add local users with a username, email, and password. Leave the optional
   phone-number field empty.
3. Create an **OIDC Web Application** named BioOps.
4. Assign only the local users or user-pool group that may access BioOps.

Set `BIOOPS_AUTH_ALLOWED_DOMAIN` to the user pool's login domain and add each
pool username to the BioOps authorized-user database. A personal test organization
does not prove Genotek employment and should not claim control of
`genotek.ru`. Production Genotek access must instead use Genotek's Identity
Hub organization and assigned corporate users or groups.

Configure the OIDC application with these settings:

- Redirect URI: the exact production callback below.
- Scopes: `openid`, `email`, and `profile`.
- Client authentication: `client_secret_post`.
- PKCE: required.
- Users and groups: assign only the users who may use BioOps.

The exact production redirect URI is:

```text
https://bioops.84-201-181-221.sslip.io/auth/sso/callback
```

From the Identity Hub application overview, copy its **OpenID Configuration**
URL and **ClientID**, then create and copy an application secret. Put those
three values in `bioops-secrets` as shown above. See the
[Yandex Identity Hub OIDC application guide](https://yandex.cloud/en/docs/organization/operations/applications/oidc-create).

The browser redirects to the configured Identity Hub organization, exchanges the returned code on the
server using PKCE, verifies the signed ID token against Identity Hub's JWKS,
and checks its issuer, audience, expiry, nonce, and subject. BioOps uses the
OIDC `preferred_username` claim as the pool identity, with the email claim as a
fallback for providers that do not return a username. It creates a session only
when that identifier belongs to `BIOOPS_AUTH_ALLOWED_DOMAIN` **and** is enabled
in the `authorized_emails` table. The authorized-user directory, identities,
and hashed opaque sessions are stored in
`/data/bioops_auth.sqlite3` on the existing PVC.

Manage the employee directory through the running API pod:

```bash
kubectl -n bioops-dev exec deployment/bioops-api -c bioops-api -- \
  python -m bioops.api.auth_admin add person@genotek.ru --name "Person Name"

kubectl -n bioops-dev exec deployment/bioops-api -c bioops-api -- \
  python -m bioops.api.auth_admin list

kubectl -n bioops-dev exec deployment/bioops-api -c bioops-api -- \
  python -m bioops.api.auth_admin disable person@genotek.ru
```

For bulk provisioning, copy a CSV containing `email,display_name` into the pod
and import it:

```bash
POD="$(kubectl -n bioops-dev get pod -l app=bioops-api \
  -o jsonpath='{.items[0].metadata.name}')"
kubectl -n bioops-dev cp employees.csv "$POD:/tmp/employees.csv" -c bioops-api
kubectl -n bioops-dev exec "$POD" -c bioops-api -- \
  python -m bioops.api.auth_admin import-csv /tmp/employees.csv
```

Disabling an employee also revokes that employee's existing BioOps sessions.
`BIOOPS_AUTH_BOOTSTRAP_EMAILS` can contain a comma-separated initial list for
development, but it should remain empty in production after the database is
provisioned.

The deployment also enables a separate developer-code form for environments
where a Genotek Yandex account is unavailable. Set a strong value of at least
five characters in the `BIOOPS_LOCAL_ACCESS_CODE` Secret field. It creates a
fixed `BioOps Developer` identity and the same secure 12-hour session, without
using an email provider. Five failed attempts from one client within five
minutes temporarily block further attempts. Disable this path at any time with
`BIOOPS_LOCAL_ACCESS_ENABLED=false`.

For local HTTP development, configure:

```bash
YANDEX_SSO_REDIRECT_URI=http://localhost:8000/auth/sso/callback
BIOOPS_COOKIE_SECURE=false
```

Keep `BIOOPS_COOKIE_SECURE=true` in Kubernetes. OIDC state is signed and
time-limited, and browser sessions use `HttpOnly`, `Secure`, `SameSite=Lax`
cookies. Caddy now provides TLS and reverse proxying only; the old shared
basic-auth password is no longer used.

To exercise the full redirect and callback locally without corporate
credentials, start the development Identity Hub in one terminal:

```bash
PYTHONPATH=src uvicorn scripts.mock_identity_hub:app \
  --host 127.0.0.1 --port 8001
```

Then start BioOps in another terminal with the matching test-only values:

```bash
BIOOPS_SSO_ENABLED=true \
YANDEX_SSO_OPENID_CONFIGURATION_URL=http://127.0.0.1:8001/.well-known/openid-configuration \
YANDEX_SSO_CLIENT_ID=bioops-local \
YANDEX_SSO_CLIENT_SECRET=local-sso-secret \
YANDEX_SSO_REDIRECT_URI=http://127.0.0.1:8000/auth/sso/callback \
BIOOPS_SESSION_SECRET=local-session-secret-for-testing \
BIOOPS_COOKIE_SECURE=false \
BIOOPS_AUTH_DB_PATH=./data/local-sso.sqlite3 \
BIOOPS_AUTH_BOOTSTRAP_EMAILS=person@genotek.ru \
PYTHONPATH=src uvicorn bioops.api.bitrix_app:app \
  --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The local provider defaults to
`person@genotek.ru`, signs a real RS256 ID token, validates PKCE, and returns
through the same BioOps callback used by the production integration.

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

Configure the Wiki subtree in `deploy/k8s/config/runtime.env` before applying
the stack:

```text
YANDEX_WIKI_ENABLED=true
YANDEX_WIKI_ROOT_SLUG=bioops
YANDEX_WIKI_ORG_ID=YOUR_ORGANIZATION_ID
YANDEX_WIKI_ORG_HEADER=X-Org-Id
YANDEX_WIKI_AUTH_SCHEME=OAuth
```

Use `X-Cloud-Org-Id` with `Bearer` authentication for a Yandex Cloud
organization using a user IAM token. Yandex Wiki does not accept service-account
authorization. For Yandex 360, use a user OAuth token with the read-only
`wiki:read` permission. The ingestion workflow reads the configured root page
and all accessible descendants into
`bioops_knowledge_wiki`; bundled `docs/` files remain in `bioops_knowledge`.

At query time the Knowledge Agent searches the Wiki collection first. Results
below `YANDEX_WIKI_MIN_SCORE` are treated as no match and trigger the bundled
docs fallback.

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
Yandex Wiki pages are fetched when enabled
Bundled knowledge source files are found
Wiki and bundled docs collections are updated
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

Submit Master can also assess multiple batch launches across multiple kube
contexts in one request. Each target binds `batch_id`, `input_prefix`, `stage`,
`cluster_context`, and an optional `namespace`. It returns one exact
`CONFIRM MOCK MULTI-LAUNCH [...]` command for the complete target list, then
submits every target sequentially and reports successes and failures together.

When BioOps runs in Kubernetes, external contexts are read from the optional
`bioops-cluster-kubeconfig` Secret, whose `config` key contains a kubeconfig.
Every target cluster must contain the configured WorkflowTemplate, namespace,
input data, and credentials authorized to create Argo Workflows. The current
in-cluster target does not require this Secret.

---

## 16. Cluster Health CronJob

The Cluster Health schedulers are defined at:

```text
deploy/k8s/cluster-health/cronjob.yaml
deploy/k8s/cluster-health/error-cronjob.yaml
deploy/k8s/cluster-health/init-retry-cronjob.yaml
```

They run:

```text
python -m bioops.jobs.cluster_health_monitor --mode status
python -m bioops.jobs.cluster_health_monitor --mode errors
python -m bioops.jobs.init_retry_watchdog --threshold-minutes 30
```

Check the CronJob:

```bash
kubectl -n bioops-dev get \
  cronjob bioops-cluster-health-monitor bioops-cluster-error-monitor
```

The init retry watchdog runs every minute. When an Argo Pod has an unfinished
init container for strictly more than 30 minutes, it deletes that stuck Pod
attempt immediately without user confirmation. Argo recreates the attempt with
`retryPolicy: OnError` and a maximum of five retries. This watchdog does not
replace the separate D5 failed-sample retry assessment.

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
The workflow health report runs hourly, including while the pipeline is idle.
Analyzed workflow Pod error alerts run every 30 minutes and stay quiet when healthy.
The two notification CronJobs are suspended until the new image is validated.
The init retry watchdog is enabled because it is an automatic recovery control.
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
Show each active workflow, its Pods, and current pipeline steps.
```

```text
Show Kubernetes node pressure and scheduling capacity.
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
