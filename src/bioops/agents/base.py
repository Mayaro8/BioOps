from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Base class for all BioOps agents."""

    name: str
    description: str

    @abstractmethod
    def run(self, message: str) -> str:
        """Process a user message and return a response."""
        pass
