# BioOps — a multi-agent system for operating bioinformatics pipelines

Summer internship assignment 2026.

## 1. Context

At Genotek, bioinformatics processing is organized as the `pipeline-v3.0` pipeline — a sequence of steps, each living in its own repository, running on Kubernetes, and using databases (including ClickHouse), queues, and cloud functions. Processing is done in batches.

Today, operating the pipeline requires a lot of manual work: a developer/on-call engineer goes into k8s, reads logs, calculates the cost of pods and VMs, restarts failed jobs, and answers colleagues' questions like "what's happening with batch N right now" and "how does such-and-such step work".

**Goal of the internship** — design and implement **BioOps**: a multi-agent system that removes routine work from the team. It answers questions about the pipeline, performs code reviews, monitors the health of the infrastructure, manages runs, and maintains a transparent view of processing statuses.

## 2. What BioOps is (the general idea)

BioOps is not a single big bot, but **a set of specialized agents** under a single orchestrator. The user (engineer, bioinformatician, on-call) talks to the system in a chat (Telegram/Bitrix) or receives automatic alerts and reports from it.

```text
                 ┌─────────────────────────┐
      user       │      Orchestrator       │  routes the request
   ───────────►  │  (router / supervisor)  │  to the right agent
                 └────────────┬────────────┘
                              │
   ┌──────────┬──────────┬────┴─────┬──────────┬──────────────┐
   ▼          ▼          ▼          ▼          ▼              ▼
 Knowledge  Review   Cluster    Submit    Infra/Cost     Batch
  Agent     Agent    Health     Master    Monitoring     Status
                     Agent      Agent     Agents         Agent
   │          │          │          │          │              │
   └──────────┴──────────┴────┬─────┴──────────┴──────────────┘
                              ▼
                          Tools:
        k8s API · GitHub API · Yandex Cloud API · ClickHouse ·
        queues · Cloud Functions · vector DB (docs) · status DB
```

Key principles:
- **Agent = role + a set of tools.** Each agent can call a limited set of tools and owns its area.
- **Two modes of operation:** reactive (responds to a user request) and proactive (scheduled periodic health checks + alerts).
- **Every alert/report is short and actionable:** what happened, where, how critical, and what action is suggested.

## 3. Glossary

| Term | Meaning |
|---|---|
| `pipeline-v3.0` | The bioinformatics pipeline — a sequence of processing steps. |
| Step | A single stage of the pipeline, living in its own git repository. |
| Batch | A set of samples passing through the pipeline. |
| Submit master | A service/process that launches processing (submits jobs) based on a config. |
| Pod | A unit of execution in Kubernetes. |
| CH | ClickHouse — an analytical database. |
| Compute Cloud | The virtual machines service (Yandex Cloud). |
| Cloud Functions | Serverless cloud functions (Yandex Cloud). |
| MR / PR | Merge / Pull Request. |

## 4. Functional requirements (epics)

The requirements are grouped into epics. Each epic contains user scenarios. The priority (P0/P1/P2) defines the implementation order, see the "Stages" section.

### Epic A. Knowledge Agent — pipeline expertise `P0`

A "documentation" agent that knows how the pipeline works.

- **A1.** Gives an overview of the `pipeline-v3.0` steps: which steps exist, in what order they run, and what each is responsible for.
- **A2.** Answers questions about a specific step and always attaches a link to the step's documentation and repository:
  - input data;
  - output data;
  - how it works;
  - run parameters.
- **A3.** The knowledge source is indexed documentation and step repositories (RAG: vector DB + links to primary sources). The answer always contains a link to the primary source.

### Epic B. Review Agent — code review of steps `P1`

- **B1.** On request, performs a review of a specific step based on its repository.
- **B2.** On request, checks the open MRs in a step's repository.
- **B3.** Performs a review based on a provided link to a specific MR.
- **B4.** The review result is a structured comment: found issues, risks, style/logic remarks, and suggestions. No fluff.

### Epic C. Cluster Health Agent — k8s cluster health `P0`

Proactive + reactive.

- **C1.** Periodic health check of the bioinformatics k8s clusters.
- **C2.** Log analysis for errors.
- **C3.** Reports which pipeline step is currently running.
- **C4.** Details: pod statuses, their cost, and an estimated ETA to completion of the current step.
- **C5.** If something is running — sends a short periodic status report.

### Epic D. Submit Master Agent — launching and monitoring processing `P1`

- **D1.** Generates a config for the submit master.
- **D2.** Launches the submit master.
- **D3.** Monitors the submit master: logs, errors, statuses, cost, ETA to completion.
- **D4.** Sends a report on failed pods.
- **D5.** On request, restarts failed pods.

### Epic E. Infra & Cost Monitoring — infrastructure monitoring `P1`

Several proactive monitors with alerts.

- **E1. VMs in Compute Cloud.** Periodic check of VM cost. Raises an **alert** if an "expensive" VM (more than 50,000 ₽/month **or** with a GPU) has been running for more than 3 hours.
- **E2. Pipeline DB hosts.** Periodic health check: CPU, RAM, ClickHouse mutations. Alert on suspicious values.
- **E3. Queues.** Periodic health check: if a queue is not being drained for a long time or is being drained too slowly — alert.
- **E4. Cloud functions.** Periodic health check of the bioinformatics Cloud Functions: alert on a critical load increase or errors in the logs.

### Epic F. Batch Status Agent — batch processing statuses `P1`

- **F1.** Populates a table in the database with batch processing statuses.
- **F2.** Synchronizes the table with a Google Doc (two-way or one-way — to be confirmed with the mentor).
- **F3.** Answers questions about the status of any batch.

## 5. Non-functional requirements

- **Extensibility.** Adding a new agent/tool/monitor should not require rewriting the core.
- **Configurability.** Alert thresholds (50,000 ₽, 3 hours, queue drain rate, etc.), schedules, and the list of clusters/repositories live in config, not in code.
- **Observability.** Logging of agent actions; it is clear which agent called what and why.
- **Security.** Secrets (k8s, GitHub, cloud tokens) go through environment variables / a secret manager, not in code. Actions with side effects (restarting pods, launching the submit master) require explicit confirmation.
- **LLM cost.** Reasonable token usage: caching, concise prompts, RAG instead of "load everything into the context".

## 6. Recommended stack

> The final choice is up to the student and the mentor. The list below is a starting point.

- **Language:** Python 3.11+.
- **Agent orchestration:** LangGraph / LangChain or an equivalent with tool-calling.
- **LLM:** as agreed with the mentor (whatever is available inside the company's environment).
- **RAG:** a vector DB (Qdrant / pgvector / Chroma) for step documentation.
- **Integrations:** Kubernetes Python client, GitHub API (PyGithub), Yandex Cloud SDK/CLI, ClickHouse client, queue client.
- **Interface:** a Telegram/Bitrix bot + webhook for alerts.
- **Scheduler:** APScheduler / cron / k8s CronJob for periodic checks.
- **Status storage:** a relational DB + synchronization with the Google Sheets API.

## 7. Internship stages

Each stage ends with a working demo and a code review with the mentor.

### Stage 0. Onboarding and design (week 1)
- Get access (see section 9), study `pipeline-v3.0`.
- Write a **design document**: BioOps architecture, the list of agents and tools, the chosen stack, the data schema for batch statuses.
- Set up the project skeleton: the orchestrator + a single "echo" agent, configs, logging.

### Stage 1. MVP — knowledge + cluster health (weeks 2–3) `P0`
- Epic A (Knowledge Agent) in full.
- Epic C (Cluster Health Agent): C1–C5.
- Chat interface and basic alerts.

### Stage 2. Launching and managing processing (weeks 4–5) `P1`
- Epic D (Submit Master Agent).
- Epic F (Batch Status Agent).

### Stage 3. Infrastructure monitoring and review (weeks 6–7) `P1`
- Epic E (Infra & Cost Monitoring): E1–E4.
- Epic B (Review Agent).

### Stage 4. Stabilization and handover (week 8)
- Polishing, tests, documentation, final demo.
- Stretch goals (if time remains): policy-based auto-restart, a dashboard, proactive cost optimization recommendations.

> The timeline is approximate and is adjusted with the mentor to the real duration of the internship.

## 8. Definition of Done

A feature is considered done when:
- the scenario from the epic is reproducible in a demo on real (or as close to real as possible) data;
- there is config for all thresholds/schedules, with no "magic" in the code;
- actions with side effects require confirmation and are logged;
- alerts/reports are concise and contain "what happened / where / criticality / what to do";
- the code has passed the mentor's review, and there are basic tests for the key logic;
- the README/docs are updated: how to run, how to configure, how to add a new agent.

## 9. What is needed from the mentor (access and inputs)

- [ ] Description/documentation of `pipeline-v3.0` and the list of step repositories.
- [ ] Access to the k8s clusters (read-only for health checks; pod restart permissions separately).
- [ ] Access to the GitHub organization (read access to repositories and MRs).
- [ ] Access to Yandex Cloud: Compute Cloud (VM cost), Cloud Functions, billing.
- [ ] Access to the DB hosts and ClickHouse (metrics, mutations).
- [ ] Access to the queue system.
- [ ] A description of the submit master: config format, how it is launched, where the logs are.
- [ ] Access to the LLM provider inside the company's environment.
- [ ] An alert channel (Telegram/Bitrix) and a Google Doc for batch statuses.
- [ ] Agreed alert thresholds and check intervals.

## 10. Internship deliverables

1. The `bio-ops` repository with a working multi-agent system (at minimum — the P0 epics, the goal — P0+P1).
2. A design document and operational documentation.
3. A demo of the key scenarios.
4. Deployment and configuration instructions.
