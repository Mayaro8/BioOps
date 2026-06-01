from bioops.agents.base import BaseAgent


class EchoAgent(BaseAgent):
    """Simple test agent that repeats the user message."""

    name = "echo"
    description = "Repeats the user message. Used to test the orchestrator."

    def run(self, message: str) -> str:
        return f"Echo Agent received: {message}"
