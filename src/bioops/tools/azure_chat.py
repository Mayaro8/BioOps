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
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> Any:
    """Create a chat completion, tolerant of deployment-specific parameters.

    The call is retried a bounded number of times, each time dropping (or
    translating) exactly one parameter that the target deployment reports as
    unsupported. This transparently handles:

    * ``max_completion_tokens`` vs legacy ``max_tokens``.
    * ``reasoning_effort`` on reasoning models vs deployments that don't
      support it at all (it is simply omitted in that case).

    Only "unsupported parameter/value" (HTTP 400) responses trigger a retry;
    genuine failures such as timeouts are raised immediately so callers keep
    full control over retry/degradation behavior.

    Args:
        client: An ``AzureOpenAI`` (or compatible OpenAI) client.
        model: Deployment / model name.
        messages: Chat messages payload.
        max_completion_tokens: Desired maximum number of completion tokens.
        reasoning_effort: Optional reasoning effort hint (e.g. ``"low"``) for
            reasoning models. Ignored on deployments that don't support it.
        **kwargs: Any additional parameters forwarded to the OpenAI SDK.

    Returns:
        The OpenAI chat-completion response object.
    """
    request: dict[str, Any] = dict(kwargs)
    if max_completion_tokens is not None:
        request["max_completion_tokens"] = max_completion_tokens
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort

    # At most one adjustment per adjustable parameter, plus the final attempt.
    for _ in range(3):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                **request,
            )
        except TypeError:
            # Installed SDK signature does not accept max_completion_tokens;
            # translate to the legacy max_tokens keyword and retry.
            if "max_completion_tokens" in request:
                request["max_tokens"] = request.pop("max_completion_tokens")
                continue
            raise
        except Exception as error:  # noqa: BLE001 - inspected and re-raised.
            if "max_completion_tokens" in request and _is_unsupported_parameter_error(
                error, "max_completion_tokens"
            ):
                request["max_tokens"] = request.pop("max_completion_tokens")
                continue
            if "reasoning_effort" in request and _is_unsupported_parameter_error(
                error, "reasoning_effort"
            ):
                request.pop("reasoning_effort")
                continue
            raise

    return client.chat.completions.create(
        model=model,
        messages=messages,
        **request,
    )


def _is_unsupported_parameter_error(error: Exception, parameter: str) -> bool:
    """Return True when ``error`` reports ``parameter`` as unsupported.

    Matches Azure OpenAI 400 responses without being tied to a specific SDK
    exception class, e.g.:

    * "Unsupported parameter: 'max_completion_tokens' is not supported with
      this model. Use 'max_tokens' instead."
    * "Unsupported value: 'reasoning_effort' does not support 'minimal' with
      this model."
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
