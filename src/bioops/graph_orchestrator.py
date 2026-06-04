from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from bioops.agents.echo_agent import EchoAgent
from bioops.agents.knowledge_agent import KnowledgeAgent


class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


echo_agent = EchoAgent()
knowledge_agent = KnowledgeAgent()


def router_node(state: BioOpsState) -> BioOpsState:
    message = state["message"].lower()

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

    selected_agent = (
        "knowledge"
        if any(keyword in message for keyword in knowledge_keywords)
        else "echo"
    )

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


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("echo", echo_node)
    graph.add_node("knowledge", knowledge_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "echo": "echo",
            "knowledge": "knowledge",
        },
    )

    graph.add_edge("echo", END)
    graph.add_edge("knowledge", END)

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