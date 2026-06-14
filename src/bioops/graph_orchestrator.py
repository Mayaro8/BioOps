from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from bioops.agents.echo_agent import EchoAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.review_agent import ReviewAgent
from bioops.agents.batch_status_agent import BatchStatusAgent


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


echo_agent = EchoAgent()
knowledge_agent = KnowledgeAgent()
review_agent = ReviewAgent()

# Lazy-loaded so pytest/imports do not load Kubernetes config immediately.
cluster_health_agent: ClusterHealthAgent | None = None
batch_status_agent: BatchStatusAgent | None = None


def router_node(state: BioOpsState) -> BioOpsState:
    message = state["message"].lower()

    message_tokens = set(
        message.replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
        .replace(".", " ")
        .replace(",", " ")
        .split()
    )

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
        "cost",
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

    if any(keyword in message for keyword in batch_status_keywords):
        selected_agent = "batch_status"
    elif any(keyword in message for keyword in cluster_health_keywords):
        selected_agent = "cluster_health"
    elif (
        any(keyword in message for keyword in review_keywords)
        or bool(review_tokens.intersection(message_tokens))
    ):
        selected_agent = "review"
    elif any(keyword in message for keyword in knowledge_keywords):
        selected_agent = "knowledge"
    else:
        selected_agent = "echo"

    return {
        **state,
        "selected_agent": selected_agent,
    }


def route_after_router(state: BioOpsState) -> str:
    return state["selected_agent"]


def echo_node(state: BioOpsState) -> BioOpsState:
    response = echo_agent.run(state["message"])

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


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("echo", echo_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("cluster_health", cluster_health_node)
    graph.add_node("review", review_node)
    graph.add_node("batch_status", batch_status_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "echo": "echo",
            "knowledge": "knowledge",
            "cluster_health": "cluster_health",
            "review": "review",
            "batch_status": "batch_status",
        },
    )

    graph.add_edge("echo", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("cluster_health", END)
    graph.add_edge("review", END)
    graph.add_edge("batch_status", END)

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