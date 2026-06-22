from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from bioops.agents.general_agent import GeneralAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.review_agent import ReviewAgent
from bioops.tools.llm_router import LLMRouterTool


ROUTABLE_AGENTS = {"general", "knowledge", "cluster_health", "review"}


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


general_agent = GeneralAgent()
knowledge_agent = KnowledgeAgent()
review_agent = ReviewAgent()
llm_router_tool = LLMRouterTool()

cluster_health_agent: ClusterHealthAgent | None = None


def keyword_route(message: str) -> str:
    text = message.lower()

    if any(word in text for word in ["review", "pull request", "merge request", "pr", "diff", "code changes"]):
        return "review"

    if any(word in text for word in ["cluster", "k8s", "kubernetes", "pod", "pods", "health", "logs", "errors"]):
        return "cluster_health"

    if any(word in text for word in ["pipeline", "step", "docs", "documentation", "bam", "gvcf", "vcf", "explain"]):
        return "knowledge"

    return "general"


def router_node(state: BioOpsState) -> BioOpsState:
    try:
        selected_agent = llm_router_tool.route(state["message"]).agent
    except Exception:
        selected_agent = keyword_route(state["message"])

    if selected_agent not in ROUTABLE_AGENTS:
        selected_agent = "general"

    return {**state, "selected_agent": selected_agent}


def route_after_router(state: BioOpsState) -> str:
    selected_agent = state["selected_agent"]

    if selected_agent not in ROUTABLE_AGENTS:
        return "general"

    return selected_agent


def general_node(state: BioOpsState) -> BioOpsState:
    return {**state, "response": general_agent.run(state["message"])}


def knowledge_node(state: BioOpsState) -> BioOpsState:
    return {**state, "response": knowledge_agent.run(state["message"])}


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

    return {**state, "response": response}


def review_node(state: BioOpsState) -> BioOpsState:
    return {**state, "response": review_agent.run(state["message"])}


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("general", general_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("cluster_health", cluster_health_node)
    graph.add_node("review", review_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "general": "general",
            "knowledge": "knowledge",
            "cluster_health": "cluster_health",
            "review": "review",
        },
    )

    graph.add_edge("general", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("cluster_health", END)
    graph.add_edge("review", END)

    return graph.compile()


class LangGraphOrchestrator:
    def __init__(self):
        self.graph = build_graph()

    def route(self, message: str) -> str:
        result = self.graph.invoke(
            {"message": message, "selected_agent": "", "response": ""}
        )
        return result["response"]
