import pytest

from bioops.tools.llm_router import ALLOWED_AGENTS, LLMRouterTool


def test_parse_valid_router_json():
    tool = LLMRouterTool()

    decision = tool._parse_response(
        '{"agent": "cluster_health", "reason": "pod status question"}'
    )

    assert decision.agent == "cluster_health"
    assert decision.reason == "pod status question"


def test_parse_router_json_code_fence():
    tool = LLMRouterTool()

    decision = tool._parse_response(
        '```json\n{"agent": "review", "reason": "code review"}\n```'
    )

    assert decision.agent == "review"


def test_parse_rejects_removed_echo_agent():
    tool = LLMRouterTool()

    with pytest.raises(ValueError):
        tool._parse_response('{"agent": "echo", "reason": "removed"}')


def test_route_raises_when_azure_is_not_configured():
    tool = LLMRouterTool()
    tool.enabled = False
    tool.client = None

    with pytest.raises(RuntimeError):
        tool.route("hello")


def test_allowed_agents_are_only_current_agents():
    assert ALLOWED_AGENTS == {
        "general",
        "knowledge",
        "cluster_health",
        "review",
    }
