from bioops import graph_orchestrator as go
from bioops.tools.llm_router import DEFAULT_ALLOWED_AGENTS


def setup_function():
    go.reset_orchestrator_cache()


def test_storage_is_a_supported_top_level_router_destination():
    assert "storage" in DEFAULT_ALLOWED_AGENTS
    assert "storage" in go.SUPPORTED_AGENTS


def test_storage_can_be_enabled_from_agents_configuration():
    enabled = go.get_enabled_agent_names(
        {
            "agents": {
                "general": {"enabled": True},
                "storage": {"enabled": True},
            }
        }
    )
    assert "storage" in enabled


def test_storage_node_calls_bucket_agent(monkeypatch):
    class FakeBucketAgent:
        def run(self, message):
            return f"bucket:{message}"

    monkeypatch.setattr(go, "storage_agent", FakeBucketAgent())
    assert go.storage_node({"message": "list objects", "selected_agent": "storage", "response": ""}) == {
        "response": "bucket:list objects"
    }
