from __future__ import annotations

import inspect
import sys
from typing import Any

from bioops import graph_orchestrator


def _extract_response(result: Any) -> str:
    if isinstance(result, dict):
        return str(
            result.get("response")
            or result.get("answer")
            or result.get("output")
            or result
        )

    return str(result)


def _invoke_runnable(runnable: Any, message: str) -> str:
    result = runnable.invoke({"message": message})
    return _extract_response(result)


def _call_function(function: Any, message: str) -> str | None:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return None

    # Only call simple public runners that accept one positional message.
    required_params = [
        param
        for param in signature.parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]

    if len(required_params) > 1:
        return None

    try:
        if len(required_params) == 0:
            result = function()
        else:
            result = function(message)
    except TypeError:
        return None

    if result is None:
        return None

    if hasattr(result, "invoke"):
        return _invoke_runnable(result, message)

    return _extract_response(result)


def _find_runnable_graph() -> Any | None:
    # Direct compiled graph/app variables.
    for attr_name in (
        "compiled_graph",
        "workflow",
        "app",
        "graph",
    ):
        runnable = getattr(graph_orchestrator, attr_name, None)
        if runnable is not None and hasattr(runnable, "invoke"):
            return runnable

    # Builder functions.
    for builder_name in (
        "build_graph",
        "create_graph",
        "get_graph",
        "compile_graph",
        "build_app",
        "create_app",
        "get_app",
        "build_workflow",
        "create_workflow",
        "get_workflow",
    ):
        builder = getattr(graph_orchestrator, builder_name, None)
        if callable(builder):
            try:
                runnable = builder()
            except TypeError:
                continue

            if runnable is not None and hasattr(runnable, "invoke"):
                return runnable

    return None


def _debug_exports() -> str:
    interesting = []

    for name in sorted(dir(graph_orchestrator)):
        lowered = name.lower()
        if any(word in lowered for word in ["graph", "run", "app", "orchestr", "workflow", "route"]):
            value = getattr(graph_orchestrator, name)
            interesting.append(
                f"- {name}: type={type(value).__name__}, callable={callable(value)}, none={value is None}"
            )

    if not interesting:
        return "- no graph/run/app/orchestrator-like exports found"

    return "\n".join(interesting)


def run_message(message: str) -> str:
    """
    Run one BioOps message through the current graph_orchestrator.

    This CLI supports the architecture branch where graph construction may be
    lazy and old LangGraphOrchestrator no longer exists.
    """

    # Public runner functions, if the graph module exposes one.
    for function_name in (
        "run_bioops",
        "run_message",
        "process_message",
        "route_message",
        "ask",
        "run",
    ):
        function = getattr(graph_orchestrator, function_name, None)
        if callable(function):
            response = _call_function(function, message)
            if response is not None:
                return response

    runnable = _find_runnable_graph()
    if runnable is not None:
        return _invoke_runnable(runnable, message)

    raise RuntimeError(
        "Could not find a runnable BioOps orchestrator entrypoint.\n\n"
        "Available graph_orchestrator exports:\n"
        f"{_debug_exports()}\n\n"
        "Fix needed: expose one stable function such as run_bioops(message) "
        "from src/bioops/graph_orchestrator.py, or expose a compiled graph/app "
        "with .invoke({'message': message})."
    )


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] in {"-h", "--help"}:
        print(
            "Usage:\n"
            "  python -m bioops.main\n"
            "  python -m bioops.main chat\n"
            "  python -m bioops.main ask <message>\n"
            "  python -m bioops.main <message>\n\n"
            "Interactive mode starts when no message is provided.\n"
        )
        return

    if not args or args[0] in {"chat", "interactive"}:
        print("BioOps interactive mode. Type 'exit' or 'quit' to stop.")
        while True:
            try:
                message = input("BioOps> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return

            if message.lower() in {"exit", "quit", "q"}:
                return

            if not message:
                continue

            print(run_message(message))
        return

    if args[0] in {"ask", "run"}:
        args = args[1:]

    message = " ".join(args).strip()
    if not message:
        raise SystemExit("No message provided.")

    print(run_message(message))


if __name__ == "__main__":
    main()
