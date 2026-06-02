The architecture is similar to the one discussed in the assignment itself, so it will have the message followed by the orchestrator, then one fo the agents. Each agent will be talking to a different Database depending on the task.
In the background, the Health Agent and the Cost and Infrastructure agents will be running in the background to check how the system works periodically ~3h.
The stack that is going to be used:
Language: Python 3.11+.
Agent orchestration: LangGraph.
LLM: ChatGPT 5.5.
XXX RAG: a vector DB (Qdrant / pgvector / Chroma) for step documentation.
Integrations: Kubernetes Python client, GitHub API (PyGithub), Yandex Cloud SDK/CLI, ClickHouse client, queue client, S3 client (boto3) + S3 inventory. They will show up as the the work progresses.
XXX Interface: a Telegram/Bitrix bot + webhook for alerts.
XXX Scheduler: APScheduler / cron / k8s CronJob for periodic checks.
XXX Status storage: a relational DB + synchronization with the Google Sheets API.
