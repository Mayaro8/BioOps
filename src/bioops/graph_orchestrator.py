from typing import TypedDict

from langgraph.graph import END, StateGraph

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.general_agent import GeneralAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.review_agent import ReviewAgent
from bioops.tools.llm_router import LLMRouterTool


ROUTABLE_AGENTS = {"general", "knowledge", "cluster_health", "review"}
ROUTING_ERROR = "routing_error"


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


general_agent: GeneralAgent | None = None
knowledge_agent: KnowledgeAgent | None = None
review_agent: ReviewAgent | None = None
cluster_health_agent: ClusterHealthAgent | None = None

llm_router_tool = LLMRouterTool()


def get_general_agent() -> GeneralAgent:
    global general_agent

    if general_agent is None:
        general_agent = GeneralAgent()

    return general_agent


def get_knowledge_agent() -> KnowledgeAgent:
    global knowledge_agent

    if knowledge_agent is None:
        knowledge_agent = KnowledgeAgent()

    return knowledge_agent


def get_review_agent() -> ReviewAgent:
    global review_agent

    if review_agent is None:
        review_agent = ReviewAgent()

    return review_agent


def get_cluster_health_agent() -> ClusterHealthAgent:
    global cluster_health_agent

    if cluster_health_agent is None:
        cluster_health_agent = ClusterHealthAgent()

    return cluster_health_agent


def router_node(state: BioOpsState) -> dict:
    """
    Route requests using only the LLM router.

    No keyword fallback is used. If the LLM router is unavailable, invalid,
    or misconfigured, return a clear routing error instead of guessing.
    """
    try:
        decision = llm_router_tool.route(state["message"])
    except Exception as error:
        return {
            "selected_agent": ROUTING_ERROR,
            "response": _format_routing_error(
                f"{type(error).__name__}: {error}"
            ),
        }

    selected_agent = decision.agent

    if selected_agent not in ROUTABLE_AGENTS:
        return {
            "selected_agent": ROUTING_ERROR,
            "response": _format_routing_error(
                f"LLM router returned unsupported agent: {selected_agent}"
            ),
        }

    return {
        "selected_agent": selected_agent,
        "response": "",
    }


def route_after_router(state: BioOpsState) -> str:
    selected_agent = state.get("selected_agent", ROUTING_ERROR)

    if selected_agent in ROUTABLE_AGENTS:
        return selected_agent

    return ROUTING_ERROR


def general_node(state: BioOpsState) -> dict:
    return {"response": get_general_agent().run(state["message"])}


def knowledge_node(state: BioOpsState) -> dict:
    return {"response": get_knowledge_agent().run(state["message"])}


def cluster_health_node(state: BioOpsState) -> dict:
    return {"response": get_cluster_health_agent().run(state["message"])}


def review_node(state: BioOpsState) -> dict:
    return {"response": get_review_agent().run(state["message"])}


def routing_error_node(state: BioOpsState) -> dict:
    return {
        "response": state.get("response")
        or _format_routing_error("Unknown routing failure.")
    }


def _format_routing_error(error: str) -> str:
    return "\n".join(
        [
            "BioOps routing failed",
            "",
            "Status: routing_error",
            f"Error: {error}",
            "",
            "The orchestrator now uses LLM-only routing.",
            "No keyword fallback was used.",
            "No agent was started.",
        ]
    )


graph_builder = StateGraph(BioOpsState)

graph_builder.add_node("router", router_node)
graph_builder.add_node("general", general_node)
graph_builder.add_node("knowledge", knowledge_node)
graph_builder.add_node("cluster_health", cluster_health_node)
graph_builder.add_node("review", review_node)
graph_builder.add_node(ROUTING_ERROR, routing_error_node)

graph_builder.set_entry_point("router")

graph_builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "general": "general",
        "knowledge": "knowledge",
        "cluster_health": "cluster_health",
        "review": "review",
        ROUTING_ERROR: ROUTING_ERROR,
    },
)

graph_builder.add_edge("general", END)
graph_builder.add_edge("knowledge", END)
graph_builder.add_edge("cluster_health", END)
graph_builder.add_edge("review", END)
graph_builder.add_edge(ROUTING_ERROR, END)

graph = graph_builder.compile()


def run_graph(message: str) -> str:
    result = graph.invoke(
        {
            "message": message,
            "selected_agent": ROUTING_ERROR,
            "response": "",
        }
    )

    return result.get("response", "")
