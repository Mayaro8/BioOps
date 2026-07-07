import pytest

from bioops.tools.llm_router import DEFAULT_ALLOWED_AGENTS, LLMRouterTool


def test_default_allowed_agents_are_supported_agents():
    assert DEFAULT_ALLOWED_AGENTS == {
        "general",
        "knowledge",
        "cluster_health",
        "review",
        "submit_master",
        "batch_status",
        "storage",
        "infra_cost",
    }


def test_parse_valid_router_json():
    tool = LLMRouterTool()
    decision = tool._parse_response(
        '{"agent": "knowledge", "reason": "User asks about documentation."}'
    )
    assert decision.agent == "knowledge"
    assert decision.reason == "User asks about documentation."


def test_parse_submit_master_router_json():
    tool = LLMRouterTool()
    decision = tool._parse_response(
        '{"agent": "submit_master", "reason": "User asks about retry."}'
    )
    assert decision.agent == "submit_master"


def test_parse_batch_status_router_json():
    tool = LLMRouterTool()
    decision = tool._parse_response(
        '{"agent": "batch_status", "reason": "User asks about failed batches."}'
    )
    assert decision.agent == "batch_status"


def test_parse_storage_router_json():
    tool = LLMRouterTool()
    decision = tool._parse_response(
        '{"agent": "storage", "reason": "User asks for bucket size."}'
    )
    assert decision.agent == "storage"


def test_parse_json_from_markdown_block():
    tool = LLMRouterTool()
    decision = tool._parse_response(
        """```json
{"agent": "cluster_health", "reason": "User asks about failed pods."}
```"""
    )
    assert decision.agent == "cluster_health"


def test_rejects_disabled_agent():
    tool = LLMRouterTool(allowed_agents={"general", "knowledge"})
    with pytest.raises(ValueError, match="disabled or unsupported agent"):
        tool._parse_response(
            '{"agent": "review", "reason": "User asks for code review."}'
        )


def test_constructor_rejects_unknown_agent():
    with pytest.raises(ValueError, match="Unsupported router agents configured"):
        LLMRouterTool(allowed_agents={"general", "fake_agent"})


def test_general_is_always_allowed():
    tool = LLMRouterTool(allowed_agents={"knowledge"})
    assert "general" in tool.allowed_agents
    assert "knowledge" in tool.allowed_agents


def test_prompt_lists_only_enabled_agents():
    tool = LLMRouterTool(allowed_agents={"general", "knowledge"})
    prompt = tool._build_prompt("review this repository")
    assert "- general:" in prompt
    assert "- knowledge:" in prompt
    assert "- review:" not in prompt
    assert "- cluster_health:" not in prompt
    assert "- submit_master:" not in prompt
    assert "- storage:" not in prompt
    assert '"agent": "general|knowledge"' in prompt


def test_prompt_contains_submit_master_d1_to_d5_guidance():
    tool = LLMRouterTool(allowed_agents={"general", "submit_master"})
    prompt = tool._build_prompt("retry failed submit master workflow")
    assert "D1" in prompt
    assert "D2" in prompt
    assert "D3" in prompt
    assert "D4" in prompt
    assert "D5" in prompt
    assert "safe retry" in prompt


def test_prompt_contains_batch_status_guidance():
    tool = LLMRouterTool(allowed_agents={"general", "batch_status"})
    prompt = tool._build_prompt("show failed batches")
    assert "latest batch status" in prompt
    assert "failed batches" in prompt
    assert "completed batches" in prompt
    assert "stale" in prompt
    assert '"agent": "batch_status|general"' in prompt


def test_prompt_contains_storage_guidance():
    tool = LLMRouterTool(allowed_agents={"general", "storage"})
    prompt = tool._build_prompt("list vcf.gz objects")
    assert "- storage:" in prompt
    assert "storage classes" in prompt
    assert '"agent": "general|storage"' in prompt
