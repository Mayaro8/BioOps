import logging

from bioops.agents.echo_agent import EchoAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Routes user requests to the correct agent."""

    def __init__(self):
        self.agents = {
            "echo": EchoAgent()
        }

    def route(self, message: str) -> str:
        logger.info("Received message: %s", message)

        agent = self.agents["echo"]

        logger.info("Routing message to agent: %s", agent.name)

        response = agent.run(message)

        logger.info("Agent response generated")

        return response
