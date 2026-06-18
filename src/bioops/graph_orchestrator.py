from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from bioops.agents.general_agent import GeneralAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.review_agent import ReviewAgent
from bioops.agents.batch_status_agent import BatchStatusAgent
from bioops.agents.submit_master_agent import SubmitMasterAgent
from bioops.agents.storage_agent import StorageAgent
from bioops.agents.infra_cost_agent import InfraCostAgent
from bioops.tools.llm_router import LLMRouterTool


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


general_agent = GeneralAgent()
knowledge_agent = KnowledgeAgent()
review_agent = ReviewAgent()
submit_master_agent = SubmitMasterAgent()
storage_agent = StorageAgent()
infra_cost_agent = InfraCostAgent()
llm_router_tool = LLMRouterTool()

# Lazy-loaded so pytest/imports do not load Kubernetes config immediately.
cluster_health_agent: ClusterHealthAgent | None = None
batch_status_agent: BatchStatusAgent | None = None


def _message_tokens(message: str) -> set[str]:
    return set(
        message.replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
        .replace(".", " ")
        .replace(",", " ")
        .split()
    )


def keyword_route(message: str) -> str:
    """Deterministic fallback router used when LLM routing is unavailable."""

    normalized_message = message.lower()
    message_tokens = _message_tokens(normalized_message)

    submit_master_keywords = [
        "submit master",
        "submit job",
        "submit batch",
        "submit sample",
        "launch job",
        "launch batch",
        "launch sample",
        "start job",
        "start batch",
        "start pipeline",
        "run pipeline",
        "prepare submission",
        "prepare submit",
        "dry run submission",
        "dry-run submission",
    ]

    storage_keywords = [
        "storage",
        "bucket",
        "object storage",
        "s3",
        "inventory",
        "prefix",
        "prefixes",
        "file count",
        "files count",
        "count files",
        "total size",
        "storage size",
        "bam files",
        "cram files",
        "vcf files",
        "fastq files",
    ]

    infra_cost_keywords = [
        "infra",
        "infrastructure",
        "cloud cost",
        "cost monitoring",
        "vm cost",
        "yandex",
        "yandex cloud",
        "yc",
        "gpu",
        "billing",
        "clickhouse",
        "queue",
        "queues",
        "cloud function",
        "cloud functions",
        "expensive vm",
        "monitor cost",
    ]

    batch_status_keywords = [
        "batch",
        "batches",
        "batch status",
        "job status",
        "jobs",
        "progress",
        "failed batch",
        "running batch",
        "completion",
        "completed batch",
    ]

    cluster_health_keywords = [
        "cluster",
        "k8s",
        "kubernetes",
        "pod",
        "pods",
        "health",
        "logs",
        "log",
        "error",
        "errors",
        "running",
        "status",
        "statuses",
        "eta",
        "worker",
        "workers",
        "container",
        "containers",
    ]

    review_keywords = [
        "review",
        "code review",
        "pull request",
        "merge request",
        "diff",
        "changed files",
        "changes",
        "repository review",
    ]

    review_tokens = {"pr", "mr"}

    knowledge_keywords = [
        "pipeline",
        "pipeline-v3.0",
        "step",
        "steps",
        "input",
        "inputs",
        "output",
        "outputs",
        "parameter",
        "parameters",
        "docs",
        "documentation",
        "repo",
        "repository",
        "source",
        "source code",
        "how",
        "explain",
        "purpose",
        "logic",
        "haplotype",
        "haplotype caller",
        "bam",
        "gvcf",
        "vcf",
        "variant",
        "variant calling",
    ]

    if any(keyword in normalized_message for keyword in submit_master_keywords):
        return "submit_master"

    if any(keyword in normalized_message for keyword in storage_keywords):
        return "storage"

    if any(keyword in normalized_message for keyword in infra_cost_keywords):
        return "infra_cost"

    if any(keyword in normalized_message for keyword in batch_status_keywords):
        return "batch_status"

    if any(keyword in normalized_message for keyword in cluster_health_keywords):
        return "cluster_health"

    if any(keyword in normalized_message for keyword in review_keywords) or bool(
        review_tokens.intersection(message_tokens)
    ):
        return "review"

    if any(keyword in normalized_message for keyword in knowledge_keywords):
        return "knowledge"

    return "general"


def router_node(state: BioOpsState) -> BioOpsState:
    """Route through LLM first, then fall back to deterministic routing."""

    message = state["message"]

    try:
        decision = llm_router_tool.route(message)
        selected_agent = decision.agent
    except Exception:
        selected_agent = keyword_route(message)

    return {
        **state,
        "selected_agent": selected_agent,
    }


def route_after_router(state: BioOpsState) -> str:
    return state["selected_agent"]


def general_node(state: BioOpsState) -> BioOpsState:
    response = general_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def knowledge_node(state: BioOpsState) -> BioOpsState:
    response = knowledge_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def cluster_health_node(state: BioOpsState) -> BioOpsState:
    global cluster_health_agent

    try:
        if cluster_health_agent is None:
            cluster_health_agent = ClusterHealthAgent()

        response = cluster_health_agent.run(state["message"])
    except Exception as error:
        response = (
            "Cluster Health Agent failed to connect to Kubernetes.\n\n"
            f"Error: {type(error).__name__}: {error}\n\n"
            "Check Kubernetes access, kubeconfig, and Docker volume mounts."
        )

    return {
        **state,
        "response": response,
    }


def review_node(state: BioOpsState) -> BioOpsState:
    response = review_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def batch_status_node(state: BioOpsState) -> BioOpsState:
    global batch_status_agent

    try:
        if batch_status_agent is None:
            batch_status_agent = BatchStatusAgent()

        response = batch_status_agent.run(state["message"])
    except Exception as error:
        response = (
            "Batch Status Agent failed to collect batch status.\n\n"
            f"Error: {type(error).__name__}: {error}\n\n"
            "Check Kubernetes access, kubeconfig, and Docker volume mounts."
        )

    return {
        **state,
        "response": response,
    }


def submit_master_node(state: BioOpsState) -> BioOpsState:
    response = submit_master_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def storage_node(state: BioOpsState) -> BioOpsState:
    response = storage_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def infra_cost_node(state: BioOpsState) -> BioOpsState:
    response = infra_cost_agent.run(state["message"])
    return {
        **state,
        "response": response,
    }


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("general", general_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("cluster_health", cluster_health_node)
    graph.add_node("review", review_node)
    graph.add_node("batch_status", batch_status_node)
    graph.add_node("submit_master", submit_master_node)
    graph.add_node("storage", storage_node)
    graph.add_node("infra_cost", infra_cost_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "general": "general",
            "knowledge": "knowledge",
            "cluster_health": "cluster_health",
            "review": "review",
            "batch_status": "batch_status",
            "submit_master": "submit_master",
            "storage": "storage",
            "infra_cost": "infra_cost",
        },
    )

    graph.add_edge("general", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("cluster_health", END)
    graph.add_edge("review", END)
    graph.add_edge("batch_status", END)
    graph.add_edge("submit_master", END)
    graph.add_edge("storage", END)
    graph.add_edge("infra_cost", END)

    return graph.compile()


class LangGraphOrchestrator:
    def __init__(self):
        self.graph = build_graph()

    def route(self, message: str) -> str:
        result = self.graph.invoke(
            {
                "message": message,
                "selected_agent": "",
                "response": "",
            }
        )

        return result["response"]
