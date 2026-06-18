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


# User guide 

## 1. Knowledge Agent

### 1. Main repository components involved

The Knowledge Agent uses these files and modules:

```text
src/bioops/main.py
src/bioops/graph_orchestrator.py
src/bioops/agents/knowledge_agent.py
src/bioops/rag/embeddings.py
src/bioops/rag/qdrant_store.py
src/bioops/rag/chat.py
src/bioops/rag/chunking.py
src/bioops/rag/ingest.py
configs/agents.yaml
docker-compose.yml
.env.example
docs/
```

Component roles:

| Component | Role |
|---|---|
| `main.py` | Starts the BioOps CLI |
| `graph_orchestrator.py` | Routes knowledge-style questions to `KnowledgeAgent` |
| `KnowledgeAgent` | Coordinates query expansion, embedding, vector search, and final answer generation |
| `AzureEmbeddingClient` | Embeds user questions and documentation chunks |
| `QdrantKnowledgeStore` | Stores and searches vectorized documentation chunks |
| `AzureChatClient` | Generates the final natural-language answer from retrieved chunks |
| `chunking.py` | Reads and splits documents into chunks |
| `ingest.py` | Embeds and uploads document chunks into Qdrant |
| `configs/agents.yaml` | Enables and describes the Knowledge Agent |
| `docker-compose.yml` | Starts Qdrant and the BioOps container |
| `.env` | Provides Azure OpenAI and Qdrant configuration |

---

### 2. Required tools for use

```text
Git
Docker
Docker Compose
A valid Azure OpenAI configuration
```

The project is expected to run through Docker Compose. We do not need to manually install Python packages on the host machine if they use Docker.

---

### 3. Clone the repository

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
```

### 4. Configure environment variables

Create a local `.env` file from the example file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
nano .env
```

The Knowledge Agent needs Azure OpenAI variables and Qdrant configuration.

Example `.env` values:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=your_chat_deployment

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=bioops_knowledge
```

---

### 5. Build Docker image and start Qdrant

Build the BioOps image:

```bash
docker compose build bioops
```

Start Qdrant:

```bash
docker compose up -d qdrant
```

Check running containers:

```bash
docker compose ps
```

Expected result:

```text
bioops-qdrant   running
```

The exact formatting may differ by Docker Compose version.

---

### 6. Document ingestion warning

The ingestion pipeline scans files in the `docs/` directory.

For external testing, keep test documentation files limited to:

```text
.md
.txt
.yaml
.yml
```

PDF files may not be safe for external testing unless PDF ingestion has been verified in the current branch. If a PDF is present and ingestion fails with a text decoding error, temporarily remove the PDF from `docs/` or test only with Markdown/YAML/TXT files.

Recommended minimum test document:

```text
docs/pipeline_metadata.yaml
```

---

### 7. Ingest documentation into Qdrant

Before the Knowledge Agent can answer from documentation, the docs need to be embedded and inserted into Qdrant.

Run:

```bash
docker compose run --rm bioops python -m bioops.rag.ingest
```

Expected result should mention that documents or chunks were ingested.

Example expected shape:

```text
Ingested N chunks into Qdrant collection bioops_knowledge
```

The exact number of chunks may differ depending on the current `docs/` contents.

---


### 8. Start the BioOps CLI

Run:

```bash
docker compose run --rm bioops python -m bioops.main
```

Expected startup:

```text
BioOps CLI started. Type 'exit' to quit.
You:
```

If the CLI fails with `ModuleNotFoundError`, rebuild the Docker image:

```bash
docker compose build --no-cache bioops
```

Then retry:

```bash
docker compose run --rm bioops python -m bioops.main
```

---

### 9. Knowledge Agent prompts

Use the following prompts inside the CLI.

#### Basic pipeline questions

```text
Explain pipeline-v3.0 steps.
```

```text
What are the steps in pipeline-v3.0?
```

```text
List the pipeline steps in order.
```

#### Step-specific questions

```text
What does bam to gvcf do?
```

```text
What does bam to gvcf output?
```

```text
What is the input of bam to gvcf?
```

```text
What does gvcf to vcf do?
```

```text
What is the output of gvcf to vcf?
```

#### Connection questions

```text
How are bam to gvcf and gvcf to vcf connected?
```

```text
Which step takes a gvcf file as input?
```

```text
Which step produces a vcf file?
```

#### Source-grounding questions

```text
Based on the indexed documentation, what does bam to gvcf output?
```

```text
What does the indexed knowledge base say about pipeline-v3.0?
```

---

### 10. Minimal command sequence

For convenience, the full minimal sequence for testing and then trying is:

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps

cp .env.example .env
# edit .env and add real Azure OpenAI values

docker compose build bioops
docker compose up -d qdrant
docker compose run --rm bioops python -m bioops.rag.ingest
docker compose run --rm bioops python -m pytest
docker compose run --rm bioops python -m bioops.main
```

Then test inside the CLI:

```text
Explain pipeline-v3.0 steps.
What does bam to gvcf output?
Which step takes a gvcf file as input?
What is the exact cloud cost of pipeline-v3.0?
```

# Cluster Health Agent User Guide

## 1. Cluster Health Agent

The Cluster Health Agent monitors Kubernetes pod health for BioOps pipeline workloads. It reports pod status, running pipeline steps, unhealthy pods, recent errors, container failures, and basic runtime metrics.

This agent does **not** create or manage Kubernetes clusters. It connects to an existing Kubernetes cluster using kubeconfig or in-cluster Kubernetes permissions.

---

## 2. Main Repository Components

```text
src/bioops/main.py
src/bioops/graph_orchestrator.py
src/bioops/agents/cluster_health_agent.py
src/bioops/tools/k8s_health.py
src/bioops/jobs/cluster_health_monitor.py
src/bioops/tools/alert_tool.py
configs/agents.yaml
docker-compose.yml
.env.example
scripts/run_cluster_health_monitor.sh
logs/cluster_health_monitor.log
```

| Component                       | Role                                                                         |
| ------------------------------- | ---------------------------------------------------------------------------- |
| `main.py`                       | Starts the BioOps CLI                                                        |
| `graph_orchestrator.py`         | Routes Kubernetes health requests to `ClusterHealthAgent`                    |
| `ClusterHealthAgent`            | Generates human-readable Kubernetes health reports                           |
| `K8sHealthTool`                 | Reads pod status, labels, logs, container states, and errors from Kubernetes |
| `cluster_health_monitor.py`     | Runs the Cluster Health Agent as a non-interactive monitoring job            |
| `AlertTool`                     | Sends or prints alert messages from the monitor                              |
| `run_cluster_health_monitor.sh` | Shell script for running scheduled health checks                             |
| `cluster_health_monitor.log`    | Log file for scheduled monitor output                                        |
| `docker-compose.yml`            | Runs BioOps in Docker and mounts Kubernetes configuration                    |
| `.env`                          | Stores local runtime configuration                                           |

---

## 3. Required Tools

```text
Git
Docker
Docker Compose
kubectl
A running Kubernetes cluster
A valid kubeconfig file
```

For local testing, use Minikube or Kind.

For external testing, the tester must already have access to a Kubernetes cluster. The BioOps Docker image does **not** create a Kubernetes cluster automatically.

---

## 4. Clone the Repository

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
```

---

## 5. Configure Environment Variables

Create a local `.env` file:

```bash
cp .env.example .env
```

Edit it:

```bash
nano .env
```

The Cluster Health Agent mainly needs Kubernetes access.

Azure OpenAI variables are only needed if the LLM router or general fallback agent is enabled.

Example:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_CHAT_DEPLOYMENT=your_chat_deployment
```

---

## 6. Prepare a Kubernetes Cluster

For local testing with Minikube:

```bash
minikube start
kubectl get nodes
```

Create the BioOps namespace:

```bash
kubectl create namespace bioops
```

If the namespace already exists, Kubernetes may return an error. This can be ignored.

Check the namespace:

```bash
kubectl get namespaces
```

---

## 7. Create Example Test Pods

Create a healthy pod:

```bash
kubectl run bam-to-gvcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=bam-to-gvcf \
  --command -- sleep 3600
```

Create a failing pod:

```bash
kubectl run gvcf-to-vcf-worker \
  --image=busybox \
  --namespace=bioops \
  --labels=pipeline_step=gvcf-to-vcf \
  --command -- sh -c "echo simulated failure; exit 1"
```

Check pods:

```bash
kubectl get pods -n bioops
```

Expected shape:

```text
bam-to-gvcf-worker     Running
gvcf-to-vcf-worker     Error
```

---

## 8. Build Docker Image

```bash
docker compose build bioops
```

If imports or dependencies fail:

```bash
docker compose build --no-cache bioops
```

---

## 9. Start the BioOps CLI

```bash
docker compose run --rm bioops python -m bioops.main
```

Expected startup:

```text
BioOps CLI started. Type 'exit' to quit.
You:
```

---

## 10. Cluster Health Agent CLI Prompts

Use these prompts inside the CLI.

```text
Check Kubernetes cluster health.
```

```text
Check k8s pod status.
```

```text
Are any pods failing?
```

```text
Show unhealthy pipeline workers.
```

```text
Which pipeline steps are running?
```

```text
Is bam to gvcf running?
```

```text
Is gvcf to vcf failing?
```

```text
Show recent Kubernetes errors.
```

```text
Check pod logs for failures.
```

---

## 11. Expected CLI Output

Example shape:

```text
Cluster Health Report

Total pods: 2
Running pods: 1
Unhealthy pods: 1

Pods:
- bam-to-gvcf: bam-to-gvcf-worker [Running]
- gvcf-to-vcf: gvcf-to-vcf-worker [Error]

Recent errors:
- gvcf-to-vcf-worker terminated with exit code 1
```

Actual output may differ depending on the current cluster state.

---

# Health Monitor

## 12. What the Health Monitor Does

The Health Monitor is the non-interactive monitoring layer for the Cluster Health Agent.

Unlike the BioOps CLI, it does **not** require a user prompt. It is designed to run from a script or cron job and automatically check Kubernetes cluster health at regular intervals.

Flow:

```text
cron or shell command
    ↓
scripts/run_cluster_health_monitor.sh
    ↓
python -m bioops.jobs.cluster_health_monitor
    ↓
ClusterHealthAgent
    ↓
K8sHealthTool
    ↓
cluster health report text
    ↓
AlertTool
    ↓
terminal output / log file / optional webhook alert
```

---

## 13. Run Health Monitor Manually

From the repository root:

```bash
bash scripts/run_cluster_health_monitor.sh
```

Or directly through Docker:

```bash
docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```

This does not require typing a prompt into the BioOps CLI.

---

## 14. Run Health Monitor on a Schedule

Example cron entry for running every 3 hours:

```cron
0 */3 * * * cd /home/mayar/bio-ops && bash scripts/run_cluster_health_monitor.sh >> logs/cluster_health_monitor.log 2>&1
```

This means:

```text
Every 3 hours
    ↓
run the Health Monitor script
    ↓
write output to logs/cluster_health_monitor.log
    ↓
send alert through AlertTool if configured
```

---

## 15. Bitrix24 Webhook Alerts

The Health Monitor can optionally send the cluster health report to Bitrix24.

Bitrix24 is **optional**. The monitor should still work without it.

Alert flow:

```text
Health Monitor output
    ↓
AlertTool
    ↓
Bitrix24 webhook
    ↓
Bitrix24 chat message
```

---

## 16. Bitrix24 Environment Variables

Store webhook settings in `.env`.

Example:

```bash
BIOOPS_ALERT_WEBHOOK_URL=https://your-domain.bitrix24.com/rest/<user_id>/<webhook_code>/im.message.add
BIOOPS_ALERT_DIALOG_ID=chat123
```

| Variable                   | Role                           |
| -------------------------- | ------------------------------ |
| `BIOOPS_ALERT_WEBHOOK_URL` | Bitrix24 REST webhook endpoint |
| `BIOOPS_ALERT_DIALOG_ID`   | Target Bitrix24 chat/dialog ID |

The webhook URL contains a secret token. Do **not** commit it.

---

## 17. Bitrix24 Message Shape

The alert payload should look like this:

```json
{
  "DIALOG_ID": "chat123",
  "MESSAGE": "Cluster Health Report\n\nTotal pods: 2\nRunning pods: 1\nUnhealthy pods: 1"
}
```

`DIALOG_ID` tells Bitrix24 where to post the message.

`MESSAGE` contains the health report generated by BioOps.

---

## 18. Behavior Without Bitrix24

If `BIOOPS_ALERT_WEBHOOK_URL` is not configured, the Health Monitor should still run normally.

Expected behavior:

```text
Cluster health check runs
Health report is generated
Bitrix24 alert is skipped
Output is written to terminal or logs/cluster_health_monitor.log
```

So without Bitrix24:

```text
No Bitrix24 message is sent.
The monitor should not crash.
The health report should still appear in logs.
```

This is useful for local testing, external testing, and environments where Bitrix24 alerting is not available.

---

## 19. Expected Health Monitor Behavior

The monitor should:

```text
Check Kubernetes pod health
Detect unhealthy or failed pods
Collect recent error information
Generate a cluster health summary
Send the summary through AlertTool
Post to Bitrix24 only if webhook variables are configured
Write output to logs/cluster_health_monitor.log
```

---

## 20. Troubleshooting

| Problem                   | Likely Cause                                               |
| ------------------------- | ---------------------------------------------------------- |
| `No route to host`        | Minikube is stopped or Docker cannot reach the cluster     |
| kubeconfig error          | kubeconfig is not mounted into the container               |
| no pods found             | Wrong namespace or no test pods exist                      |
| permission denied         | Kubernetes RBAC does not allow pod/log reads               |
| no Bitrix24 message       | Webhook URL or dialog ID is missing                        |
| monitor runs but no alert | AlertTool skipped webhook because configuration is missing |

Check Kubernetes directly:

```bash
kubectl get pods -n bioops
```

Check Docker execution:

```bash
docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```

Check logs:

```bash
cat logs/cluster_health_monitor.log
```

---

## 21. Minimal Local Test Sequence

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps

cp .env.example .env

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
  --command -- sh -c "echo simulated failure; exit 1"

docker compose build bioops
docker compose run --rm bioops python -m pytest
docker compose run --rm bioops python -m bioops.jobs.cluster_health_monitor
```

---

## 22. Clean Up Test Resources

```bash
kubectl delete pod bam-to-gvcf-worker -n bioops
kubectl delete pod gvcf-to-vcf-worker -n bioops
```


## 3 Review Agent User Guide

### 1. Review Agent

The Review Agent checks BioOps repositories, GitHub pull requests, open PRs, and branch comparisons. It produces a read-only review report with changed files, deterministic risks, style or logic remarks, suggestions, and optional LLM patch review.

The Review Agent does **not** post GitHub comments, does **not** approve pull requests, does **not** modify PR status, and does **not** change repository files.

---

### 2. Main Repository Components

The Review Agent uses these files and modules:

```text
src/bioops/main.py
src/bioops/graph_orchestrator.py
src/bioops/agents/review_agent.py
src/bioops/tools/github_review_tool.py
src/bioops/tools/llm_review.py
configs/agents.yaml
docker-compose.yml
.env.example
requirements.txt
```

#### Component Roles

| Component | Role |
|---|---|
| `main.py` | Starts the BioOps CLI |
| `graph_orchestrator.py` | Routes repository, PR, diff, and code-review requests to `ReviewAgent` |
| `ReviewAgent` | Coordinates local repo review, GitHub repo review, PR review, branch comparison, and report formatting |
| `GitHubReviewTool` | Parses review requests and fetches GitHub repository, PR, and branch comparison data |
| `LLMReviewTool` | Uses Azure OpenAI to perform optional patch-level review |
| `configs/agents.yaml` | Enables and describes the Review Agent |
| `docker-compose.yml` | Runs BioOps through Docker |
| `.env` | Provides GitHub and Azure OpenAI configuration |
| `requirements.txt` | Includes GitHub/OpenAI dependencies |

---

### 3. Prerequisites

The following tools are required:

```text
Git
Docker
Docker Compose
A GitHub personal access token for GitHub PR/repo review
A valid Azure OpenAI configuration for LLM patch review
```

Local repository review can run without GitHub credentials.

GitHub PR review needs:

```text
GITHUB_TOKEN
```

LLM patch review needs Azure OpenAI chat configuration.

---

### 4. Clone the Repository

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
```

---

### 5. Configure Environment Variables

Create a local `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
nano .env
```

Recommended `.env` values:

```bash
GITHUB_TOKEN=your_github_token

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_CHAT_DEPLOYMENT=your_chat_deployment
```

The GitHub token should have read access to the repositories being reviewed.

Do not commit `.env`.

---

### 6. Build Docker Image

Build the BioOps image:

```bash
docker compose build bioops
```

If dependencies or imports fail, rebuild cleanly:

```bash
docker compose build --no-cache bioops
```

### 8. Start the BioOps CLI

Run:

```bash
docker compose run --rm bioops python -m bioops.main
```

Expected startup:

```text
BioOps CLI started. Type 'exit' to quit.
You:
```

---

### 9. Review Agent Prompts

Use the following prompts inside the CLI.

#### Local Repository Review

```text
Review this repository.
```

```text
Review path=/app
```

```text
Check this repo for risks and missing tests.
```

```text
Review local changes.
```

#### GitHub Repository Overview

```text
Review repo=Mayaro8/BioOps
```

```text
Check repository repo=Mayaro8/BioOps
```

```text
Review GitHub repository repo=Mayaro8/BioOps
```

#### Open Pull Requests

```text
Check open PRs repo=Mayaro8/BioOps
```

```text
List open pull requests repo=Mayaro8/BioOps
```

```text
Show open PRs repo=Mayaro8/BioOps
```

#### Specific Pull Request Review

```text
Review repo=Mayaro8/BioOps pr=1
```

```text
Review https://github.com/Mayaro8/BioOps/pull/1
```

Replace `1` with the actual pull request number.

#### Branch Comparison

```text
Review repo=Mayaro8/BioOps base=main head=feature/my-branch
```

```text
Compare repo=Mayaro8/BioOps base=main head=feature/review-agent
```

Replace the branch names with real branches from the target repository.

---

### 10. Expected Output

For a pull request or branch comparison, the Review Agent should return a report like:

```text
GitHub PR Review Report

Status: ok
Repository: owner/repo
Subject: PR #1: title
Base branch: main
Head branch: feature/example

Changed files: N
Diff size: +A/-D

Changed files summary:
- src/example.py [modified, +10/-2]

Found issues:
- none

Risks:
- Agent code changed without corresponding test changes.

Style / logic remarks:
- Agent changes should preserve concise report formatting and safe side-effect behavior.

Suggestions:
- Run orchestrator routing tests for affected agents.

LLM patch review:
1. Verdict: ...
2. Top issues: ...
3. Risks: ...
4. Next steps: ...

Review note:
- This is a read-only review using deterministic checks plus optional LLM patch analysis.
- No GitHub comments were posted.
- No PR status was modified.
```

The exact wording may differ depending on the current implementation and the reviewed repository.

---

### 11. Missing Configuration Behavior

If `GITHUB_TOKEN` is missing, GitHub review requests should return a missing-configuration message instead of crashing.

If Azure OpenAI variables are missing, the deterministic Review Agent checks should still work, but the LLM patch review section may say that LLM review is unavailable.

This is acceptable for external testing as long as the tool fails safely and clearly.

---

### 12. Quick Start Command Sequence

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps

cp .env.example .env
# edit .env and add GITHUB_TOKEN and Azure OpenAI values if available

docker compose build bioops
docker compose run --rm bioops python -m pytest
docker compose run --rm bioops python -m bioops.main
```

Then test inside the CLI:

```text
Review path=/app
Review repo=Mayaro8/BioOps
Check open PRs repo=Mayaro8/BioOps
Review repo=Mayaro8/BioOps base=main head=feature/example
```

---

### 13. Safety Notes

The Review Agent is intended to be read-only.

Expected behavior:

```text
It can read repository metadata.
It can read pull request metadata.
It can read changed files and patch text.
It can produce review text.
It should not post comments.
It should not approve pull requests.
It should not reject pull requests.
It should not push commits.
It should not modify repository files.
```

This makes it safe for external testing with read-only GitHub access.

