# Architecture and Technology Stack

The architecture is similar to the one discussed in the assignment itself. It will have the message followed by the orchestrator, then one of the agents. Each agent will be talking to a different database depending on the task.

```text
Message
  ↓
Orchestrator
  ↓
Agent
  ↓
Database / Service
```

In the background, the **Health Agent** and the **Cost and Infrastructure Agents** will be running in the background to check how the system works periodically, approximately every **3 hours**.

---

## Stack

| Area                | Technology                                                                                                                               |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Language            | Python 3.11+                                                                                                                             |
| Agent orchestration | LangGraph                                                                                                                                |
| LLM                 | ChatGPT 5.5                                                                                                                              |
| XXX RAG             | A vector DB: Qdrant / pgvector / Chroma for step documentation                                                                           |
| Integrations        | Kubernetes Python client, GitHub API / PyGithub, Yandex Cloud SDK/CLI, ClickHouse client, queue client, S3 client / boto3 + S3 inventory |
| XXX Interface       | Telegram / Bitrix bot + webhook for alerts                                                                                               |
| XXX Scheduler       | APScheduler / cron / k8s CronJob for periodic checks                                                                                     |
| XXX Status storage  | Relational DB + synchronization with the Google Sheets API                                                                               |

