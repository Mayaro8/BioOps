from bioops import graph_orchestrator as go


class FakeDecision:
    def __init__(self, agent: str):
        self.agent = agent
        self.reason = "test"


class FakeRouter:
    def __init__(self, agent: str):
        self.agent = agent

    def route(self, message: str):
        return FakeDecision(self.agent)


class FailingRouter:
    def route(self, message: str):
        raise RuntimeError("router unavailable")


def setup_function():
    go.reset_orchestrator_cache()


def test_router_uses_llm_selected_general(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("general"))

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == "general"


def test_router_uses_llm_selected_knowledge(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("knowledge"))

    result = go.router_node(
        {
            "message": "explain the bam to gvcf pipeline step",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == "knowledge"


def test_router_uses_llm_selected_submit_master(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("submit_master"))

    result = go.router_node(
        {
            "message": "retry failed submit master workflow",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == "submit_master"


def test_router_failure_returns_routing_error_not_general(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FailingRouter())

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == go.ROUTING_ERROR
    assert "routing_error" in result["response"]
    assert "No keyword fallback was used" in result["response"]


def test_invalid_llm_agent_returns_routing_error(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("echo"))

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == go.ROUTING_ERROR
    assert "unsupported agent" in result["response"]


def test_route_after_router_rejects_removed_echo_agent():
    result = go.route_after_router(
        {
            "message": "hello",
            "selected_agent": "echo",
            "response": "",
        }
    )

    assert result == go.ROUTING_ERROR


def test_enabled_agents_loaded_from_yaml_style_config():
    config = {
        "agents": {
            "general": {"enabled": True},
            "knowledge": {"enabled": True},
            "cluster_health": {"enabled": False},
            "review": {"enabled": False},
            "submit_master": {"enabled": True},
        }
    }

    enabled = go.get_enabled_agent_names(config)

    assert enabled == {"general", "knowledge", "submit_master"}


def test_general_is_mandatory_even_if_disabled():
    config = {
        "agents": {
            "general": {"enabled": False},
            "knowledge": {"enabled": False},
            "cluster_health": {"enabled": False},
            "review": {"enabled": False},
            "submit_master": {"enabled": False},
        }
    }

    enabled = go.get_enabled_agent_names(config)

    assert enabled == {"general"}


def test_supported_enabled_agents_are_returned():
    config = {
        "agents": {
            "general": {"enabled": True},
            "knowledge": {"enabled": False},
            "batch_status": {"enabled": True},
            "submit_master": {"enabled": True},
        }
    }

    enabled = go.get_enabled_agent_names(config)

    assert enabled == {"general", "batch_status", "submit_master"}
