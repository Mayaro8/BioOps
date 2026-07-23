import os

from openai import AzureOpenAI

from bioops.tools.azure_chat import create_chat_completion


class LLMReviewError(RuntimeError):
    """Raised when mandatory LLM patch review cannot be completed."""


class LLMReviewTool:
    """Uses Azure OpenAI to perform concise architecture and code review."""

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
                timeout=60.0, max_retries=1,
            )

    def review_prompt(self, prompt: str) -> str:
        if not self.enabled or self.client is None:
            missing = []
            if not self.endpoint:
                missing.append("AZURE_OPENAI_ENDPOINT")
            if not self.api_key:
                missing.append("AZURE_OPENAI_API_KEY")
            if not self.api_version:
                missing.append("AZURE_OPENAI_API_VERSION")
            if not self.deployment:
                missing.append("AZURE_OPENAI_CHAT_DEPLOYMENT")

            missing_text = ", ".join(missing) if missing else "unknown Azure OpenAI config"
            raise LLMReviewError(
                "LLM patch review could not be started: "
                f"missing configuration: {missing_text}"
            )

        system_prompt = (
            "You are a senior bioinformatics platform engineer reviewing GitHub "
            "pull request patches for a multi-agent BioOps assistant.\n"
            "Be concise, strict, and practical.\n"
            "Focus on logic bugs, unsafe behavior, missing tests, deployment risks, "
            "and integration issues."
        )

        try:
            response = create_chat_completion(
                self.client,
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=5000,
            )
        except Exception as error:
            raise LLMReviewError(
                f"LLM patch review failed: {type(error).__name__}: {error}"
            ) from error

        content = response.choices[0].message.content
        if not content:
            raise LLMReviewError("LLM patch review failed: model returned no content.")

        return content
