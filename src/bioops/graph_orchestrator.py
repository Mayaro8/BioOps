from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

from bioops.agents.echo_agent import EchoAgent

class BioOpsState(TypedDict):
    message: str
    selected_agent: str
    response: str


echo_agent = EchoAgent()


def router_node(state: BioOpsState) -> BioOpsState:
    return {
        **state,
        "selected_agent": "echo",
    }


def echo_node(state: BioOpsState) -> BioOpsState:
    response = echo_agent.run(state["message"])

    return {
        **state,
        "response": response,
    }


def build_graph():
    graph = StateGraph(BioOpsState)

    graph.add_node("router", router_node)
    graph.add_node("echo", echo_node)

    graph.add_edge(START, "router")
    graph.add_edge("router", "echo")
    graph.add_edge("echo", END)

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