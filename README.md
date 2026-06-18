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

### 2. Main repository components involved

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

### 3. Required tools for use

```text
Git
Docker
Docker Compose
A valid Azure OpenAI configuration
```

The project is expected to run through Docker Compose. We do not need to manually install Python packages on the host machine if they use Docker.

---

### 4. Clone the repository

```bash
git clone https://github.com/Mayaro8/BioOps.git
cd BioOps
```

### 5. Configure environment variables

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

### 6. Build Docker image and start Qdrant

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

### 7. Document ingestion warning

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

### 8. Ingest documentation into Qdrant

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

### 9. Run automated tests

Run the test suite:

```bash
docker compose run --rm bioops python -m pytest
```

Expected result:

```text
passed
```

Important note:

```text
Pytest validates the current unit tests in the repository.
It does not fully prove the end-to-end RAG workflow.
Full Knowledge Agent validation still requires manual CLI testing after documentation ingestion.
```

If tests fail, record:

```text
The failing test name
The command used
The full traceback
Whether `.env` was configured
Whether Qdrant was running
Whether ingestion was already performed
```

---

### 9. Start the BioOps CLI

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

### 10. Knowledge Agent prompts

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

### 11. Minimal command sequence

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
