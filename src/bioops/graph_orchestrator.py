from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, StateGraph

from bioops.agents.cluster_health_agent import ClusterHealthAgent
from bioops.agents.general_agent import GeneralAgent
from bioops.agents.knowledge_agent import KnowledgeAgent
from bioops.agents.review_agent import ReviewAgent
from bioops.agents.submit_master_agent import SubmitMasterAgent
from bioops.tools.llm_router import LLMRouterTool
from bioops.agents.batch_status_agent import BatchStatusAgent
from bioops.agents.bucket_agent import BucketAgent
from bioops.agents.infra_cost_agent import InfraCostAgent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_CONFIG_PATH = PROJECT_ROOT / "configs" / "agents.yaml"

SUPPORTED_AGENTS = {
    "general",
    "knowledge",
    "cluster_health",
    "review",
    "batch_status",
    "submit_master",
    "storage",
    "infra_cost",
}
MANDATORY_AGENTS = {"general"}
ROUTING_ERROR = "routing_error"


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


general_agent: GeneralAgent | None = None
knowledge_agent: KnowledgeAgent | None = None
review_agent: ReviewAgent | None = None
cluster_health_agent: ClusterHealthAgent | None = None
submit_master_agent: SubmitMasterAgent | None = None
batch_status_agent: BatchStatusAgent | None = None
storage_agent: BucketAgent | None = None
infra_cost_agent: InfraCostAgent | None = None


_llm_router_tool: LLMRouterTool | None = None
llm_router_tool: Any | None = None
_active_enabled_agent_names: set[str] | None = None

graph = None


def load_agents_config(path: Path = AGENTS_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    return data if isinstance(data, dict) else {}


def get_agents_section(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config if config is not None else load_agents_config()
    agents_section = config.get("agents", config)
    return agents_section if isinstance(agents_section, dict) else {}


def get_enabled_agent_names(config: dict[str, Any] | None = None) -> set[str]:
    agents_section = get_agents_section(config)
    enabled_agents = set(MANDATORY_AGENTS)

    for agent_name in SUPPORTED_AGENTS:
        agent_config = agents_section.get(agent_name, {})
        if isinstance(agent_config, dict) and agent_config.get("enabled", False):
            enabled_agents.add(agent_name)

    return enabled_agents


def get_active_enabled_agent_names() -> set[str]:
    global _active_enabled_agent_names

    if _active_enabled_agent_names is None:
        _active_enabled_agent_names = get_enabled_agent_names()

    return set(_active_enabled_agent_names)


def get_llm_router_tool(enabled_agent_names: set[str] | None = None) -> LLMRouterTool:
    global _llm_router_tool
    global llm_router_tool

    if llm_router_tool is not None:
        return llm_router_tool

    if _llm_router_tool is None:
        _llm_router_tool = LLMRouterTool(
            allowed_agents=enabled_agent_names or get_active_enabled_agent_names()
        )

    return _llm_router_tool


def reset_orchestrator_cache() -> None:
    """Reset lazy runtime objects. Mainly useful for tests."""

    global general_agent
    global knowledge_agent
    global review_agent
    global cluster_health_agent
    global submit_master_agent
    global _llm_router_tool
    global llm_router_tool
    global _active_enabled_agent_names
    global graph
    global batch_status_agent
    global storage_agent
    global infra_cost_agent

    general_agent = None
    knowledge_agent = None
    review_agent = None
    cluster_health_agent = None
    submit_master_agent = None
    _llm_router_tool = None
    llm_router_tool = None
    _active_enabled_agent_names = None
    graph = None
    batch_status_agent = None
    storage_agent = None
    infra_cost_agent = None

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


def get_submit_master_agent() -> SubmitMasterAgent:
    global submit_master_agent
    if submit_master_agent is None:
        submit_master_agent = SubmitMasterAgent()
    return submit_master_agent


def router_node(state: BioOpsState) -> dict:
    """
    Route requests using only the LLM router.

    Enabled agents are loaded from configs/agents.yaml.
    No keyword fallback is used. If the LLM router is unavailable, invalid,
    or misconfigured, return a clear routing error instead of guessing.
    """

    enabled_agent_names = get_active_enabled_agent_names()

    try:
        decision = get_llm_router_tool(enabled_agent_names).route(state["message"])
    except Exception as error:
        return {
            "selected_agent": ROUTING_ERROR,
            "response": _format_routing_error(f"{type(error).__name__}: {error}"),
        }

    selected_agent = decision.agent
    if selected_agent not in enabled_agent_names:
        return {
            "selected_agent": ROUTING_ERROR,
            "response": _format_routing_error(
                f"LLM router returned disabled or unsupported agent: {selected_agent}"
            ),
        }

    return {"selected_agent": selected_agent, "response": ""}

def get_batch_status_agent() -> BatchStatusAgent:
    global batch_status_agent
    if batch_status_agent is None:
        batch_status_agent = BatchStatusAgent()
    return batch_status_agent

def get_storage_agent() -> BucketAgent:
    global storage_agent
    if storage_agent is None:
        storage_agent = BucketAgent()
    return storage_agent


def get_infra_cost_agent() -> InfraCostAgent:
    global infra_cost_agent
    if infra_cost_agent is None:
        infra_cost_agent = InfraCostAgent()
    return infra_cost_agent


def route_after_router(state: BioOpsState) -> str:
    selected_agent = state.get("selected_agent", ROUTING_ERROR)
    if selected_agent in get_active_enabled_agent_names():
        return selected_agent
    return ROUTING_ERROR


def general_node(state: BioOpsState) -> dict:
    return {"response": get_general_agent().run(state["message"])}

def batch_status_node(state: BioOpsState) -> dict:
    return {"response": get_batch_status_agent().run(state["message"])}


def storage_node(state: BioOpsState) -> dict:
    return {"response": get_storage_agent().run(state["message"])}


def infra_cost_node(state: BioOpsState) -> dict:
    return {"response": get_infra_cost_agent().run(state["message"])}


def knowledge_node(state: BioOpsState) -> dict:
    return {"response": get_knowledge_agent().run(state["message"])}


def cluster_health_node(state: BioOpsState) -> dict:
    return {"response": get_cluster_health_agent().run(state["message"])}


def review_node(state: BioOpsState) -> dict:
    return {"response": get_review_agent().run(state["message"])}


def submit_master_node(state: BioOpsState) -> dict:
    return {"response": get_submit_master_agent().run(state["message"])}


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
            "The orchestrator uses LLM-only routing.",
            "Enabled agents are controlled by configs/agents.yaml.",
            "No keyword fallback was used.",
            "No disabled agent was started.",
        ]
    )


def build_graph():
    graph_builder = StateGraph(BioOpsState)
    enabled_agent_names = get_active_enabled_agent_names()

    agent_nodes = {
        "general": general_node,
        "knowledge": knowledge_node,
        "cluster_health": cluster_health_node,
        "review": review_node,
        "submit_master": submit_master_node,
        "batch_status": batch_status_node,
        "storage": storage_node,
        "infra_cost": infra_cost_node,
    }

    graph_builder.add_node("router", router_node)
    graph_builder.add_node(ROUTING_ERROR, routing_error_node)

    for agent_name in sorted(enabled_agent_names):
        graph_builder.add_node(agent_name, agent_nodes[agent_name])

    graph_builder.set_entry_point("router")

    route_map = {agent_name: agent_name for agent_name in sorted(enabled_agent_names)}
    route_map[ROUTING_ERROR] = ROUTING_ERROR

    graph_builder.add_conditional_edges("router", route_after_router, route_map)

    for agent_name in sorted(enabled_agent_names):
        graph_builder.add_edge(agent_name, END)

    graph_builder.add_edge(ROUTING_ERROR, END)

    return graph_builder.compile()


def get_graph():
    global graph
    if graph is None:
        graph = build_graph()
    return graph


def run_graph(message: str) -> str:
    result = get_graph().invoke(
        {
            "message": message,
            "selected_agent": ROUTING_ERROR,
            "response": "",
        }
    )
    return result.get("response", "")
