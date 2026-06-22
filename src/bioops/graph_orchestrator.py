from typing import TypedDict

from langgraph.graph import END, StateGraph

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.general_agent import GeneralAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
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


def get_cluster_health_agent() -> ClusterHealthAgent:
    global cluster_health_agent

    if cluster_health_agent is None:
        cluster_health_agent = ClusterHealthAgent()

    return cluster_health_agent


def router_node(state: BioOpsState) -> dict:
    """
    Route requests using the LLM router only.

    We intentionally do not use substring/keyword routing here because BioOps
    prompts often contain overlapping intents such as "review logs", "explain
    failed pods", or "check pipeline docs". The LLM router should decide from
    full context.

    If the LLM router is unavailable or returns an unsupported agent, we fall
    back to the safe general agent.
    """
    try:
        selected_agent = llm_router_tool.route(state["message"]).agent
    except Exception:
        selected_agent = "general"

    if selected_agent not in ROUTABLE_AGENTS:
        selected_agent = "general"

    return {"selected_agent": selected_agent}


def route_after_router(state: BioOpsState) -> str:
    selected_agent = state.get("selected_agent", "general")

    if selected_agent not in ROUTABLE_AGENTS:
        return "general"

    return selected_agent


def general_node(state: BioOpsState) -> dict:
    return {"response": general_agent.run(state["message"])}


def knowledge_node(state: BioOpsState) -> dict:
    return {"response": knowledge_agent.run(state["message"])}


def cluster_health_node(state: BioOpsState) -> dict:
    return {"response": get_cluster_health_agent().run(state["message"])}


def review_node(state: BioOpsState) -> dict:
    return {"response": review_agent.run(state["message"])}


graph_builder = StateGraph(BioOpsState)

graph_builder.add_node("router", router_node)
graph_builder.add_node("general", general_node)
graph_builder.add_node("knowledge", knowledge_node)
graph_builder.add_node("cluster_health", cluster_health_node)
graph_builder.add_node("review", review_node)

graph_builder.set_entry_point("router")

graph_builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "general": "general",
        "knowledge": "knowledge",
        "cluster_health": "cluster_health",
        "review": "review",
    },
)

graph_builder.add_edge("general", END)
graph_builder.add_edge("knowledge", END)
graph_builder.add_edge("cluster_health", END)
graph_builder.add_edge("review", END)

graph = graph_builder.compile()


def run_graph(message: str) -> str:
    result = graph.invoke(
        {
            "message": message,
            "selected_agent": "general",
            "response": "",
        }
    )

    return result.get("response", "")
