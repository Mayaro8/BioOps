"""Azure OpenAI chat-completion helper.

Exposes a single :func:`create_chat_completion` entry point used by every
BioOps component that talks to Azure OpenAI (general agent, action router,
query rewriter, patch review).

Why this helper exists
----------------------
Different Azure OpenAI deployments disagree about how the response length is
capped:

* Newer models (e.g. ``gpt-5.x`` / reasoning models) **require**
  ``max_completion_tokens`` and reject ``max_tokens`` with an HTTP 400
  ``unsupported_parameter`` error.
* Older deployments only understand ``max_tokens``.

Callers pass a single ``max_completion_tokens`` argument and this helper
picks the parameter the target deployment actually accepts, retrying once with
the legacy name only when the service explicitly reports the modern one as
unsupported. Timeouts and other genuine failures are re-raised unchanged so
callers keep full control over retry/degradation behavior (and we never turn a
single slow call into two sequential slow calls).
"""

from __future__ import annotations

from typing import Any


def create_chat_completion(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_completion_tokens: int | None = None,
    **kwargs: Any,
) -> Any:
    """Create a chat completion tolerant of the token-limit parameter name.

    Args:
        client: An ``AzureOpenAI`` (or compatible OpenAI) client.
        model: Deployment / model name.
        messages: Chat messages payload.
        max_completion_tokens: Desired maximum number of completion tokens.
            Sent as ``max_completion_tokens`` first and, only if the deployment
            rejects that parameter, resent as ``max_tokens``.
        **kwargs: Any additional parameters forwarded to the OpenAI SDK.

    Returns:
        The OpenAI chat-completion response object.
    """
    modern_kwargs = dict(kwargs)
    if max_completion_tokens is not None:
        modern_kwargs["max_completion_tokens"] = max_completion_tokens

    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            **modern_kwargs,
        )
    except TypeError:
        # Installed SDK signature does not accept max_completion_tokens.
        pass
    except Exception as error:  # noqa: BLE001 - inspected and re-raised below.
        if not _is_unsupported_parameter_error(error, "max_completion_tokens"):
            raise

    # Fall back to the legacy max_tokens parameter for older deployments.
    legacy_kwargs = dict(kwargs)
    if max_completion_tokens is not None:
        legacy_kwargs["max_tokens"] = max_completion_tokens

    return client.chat.completions.create(
        model=model,
        messages=messages,
        **legacy_kwargs,
    )


def _is_unsupported_parameter_error(error: Exception, parameter: str) -> bool:
    """Return True when ``error`` reports ``parameter`` as unsupported/unknown.

    This matches the Azure OpenAI 400 ``unsupported_parameter`` response, e.g.
    "Unsupported parameter: 'max_completion_tokens' is not supported with this
    model." without being tied to a specific SDK exception class.
    """
    message = getattr(error, "message", "") or str(error)
    lowered = message.lower()
    mentions_parameter = parameter.lower() in lowered
    signals_unsupported = (
        "unsupported" in lowered
        or "not supported" in lowered
        or "unknown parameter" in lowered
    )
    return mentions_parameter and signals_unsupported
