import os

from openai import AzureOpenAI

from bioops.agents.base import BaseAgent
from bioops.tools.azure_chat import create_chat_completion


class GeneralAgent(BaseAgent):
    """LLM fallback agent for general or unsupported BioOps messages."""

    name = "general"
    description = (
        "Handles greetings, unclear requests, unsupported requests, and general "
        "BioOps conversation when no specialist agent is appropriate."
    )

    def __init__(self):
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_MODEL")
        )

        self.enabled = all(
            [
                self.endpoint,
                self.api_key,
                self.api_version,
                self.deployment,
            ]
        )

        self.client = None
        if self.enabled:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=20.0, max_retries=1,
            )

    def run(self, message: str) -> str:
        if not self.enabled or self.client is None:
            return (
                "BioOps understood the request, but no specialist agent matched it and "
                "the general LLM fallback is not configured.\n\n"
                "To enable general answers, configure Azure OpenAI chat variables in .env:\n"
                "- AZURE_OPENAI_ENDPOINT\n"
                "- AZURE_OPENAI_API_KEY\n"
                "- AZURE_OPENAI_API_VERSION\n"
                "- AZURE_OPENAI_CHAT_DEPLOYMENT"
            )

        prompt = "\n".join(
            [
                "Answer the user's message as the BioOps general assistant.",
                "",
                "BioOps is a multi-agent assistant for bioinformatics operations, including:",
                "- knowledge retrieval",
                "- Argo workflow Pod health monitoring",
                "- batch and pipeline status reporting",
                "- code and pull request review",
                "- storage inventory summaries",
                "- infrastructure and cost monitoring",
                "",
                "Rules:",
                "- Give a useful answer.",
                "- If the user asks for an operational action that should be handled by a specialist agent, explain which BioOps agent is more appropriate.",
                "- Do not claim that you checked Kubernetes, GitHub, storage, or cloud systems unless a specialist tool actually did it.",
                "- Keep the answer concise and practical.",
                "",
                "User message:",
                message,
            ]
        )

        try:
            response = create_chat_completion(
                self.client,
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the general fallback assistant for BioOps. "
                            "Be helpful, practical, and honest about unavailable tools."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_completion_tokens=800,
            )
        except Exception as error:
            # GeneralAgent is the router's ultimate fallback, so it must never
            # hard-fail on a slow/unavailable LLM. Return a useful static reply.
            return self._degraded_reply(error)

        return response.choices[0].message.content or self._degraded_reply(
            RuntimeError("model returned no content")
        )

    @staticmethod
    def _degraded_reply(error: Exception) -> str:
        return "\n".join(
            [
                "BioOps is temporarily unable to reach the general assistant "
                f"model ({type(error).__name__}).",
                "",
                "The request was understood, but the LLM response could not be "
                "completed right now (likely a transient Azure OpenAI timeout).",
                "",
                "You can retry shortly, or ask a specialist directly, e.g.:",
                "- workflow / pod health  -> cluster health",
                "- batch or sample status -> batch status",
                "- bucket inventory       -> storage",
                "- VM / cost questions    -> infra & cost",
                "- documentation          -> knowledge",
            ]
        )
