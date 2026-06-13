from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from bioops.agents.echo_agent import EchoAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.review_agent import ReviewAgent


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


echo_agent = EchoAgent()
knowledge_agent = KnowledgeAgent()
cluster_health_agent = ClusterHealthAgent()
review_agent = ReviewAgent()


def router_node(state: BioOpsState) -> BioOpsState:
    message = state["message"].lower()
    message_tokens = set(
        message.replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )

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

    if any(keyword in message for keyword in cluster_health_keywords):
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
    response = cluster_health_agent.run(state["message"])

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


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("echo", echo_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("cluster_health", cluster_health_node)
    graph.add_node("review", review_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "echo": "echo",
            "knowledge": "knowledge",
            "cluster_health": "cluster_health",
            "review": "review",
        },
    )

    graph.add_edge("echo", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("cluster_health", END)
    graph.add_edge("review", END)

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