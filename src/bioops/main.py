from __future__ import annotations

import sys
from typing import Any

from bioops.graph_orchestrator import run_graph
from bioops.logging_config import setup_logging


def _extract_response(result: Any) -> str:
    """Normalize graph/orchestrator output into printable text."""
    if isinstance(result, dict):
        return str(
            result.get("response")
            or result.get("answer")
            or result.get("output")
            or result
        )

    return str(result)


def run_message(message: str) -> str:
    """Run one user message through BioOps."""
    return _extract_response(run_graph(message))


def _print_help() -> None:
    print(
        "Usage:\n"
        "  python -m bioops.main\n"
        "  python -m bioops.main chat\n"
        "  python -m bioops.main ask <message>\n"
        "  python -m bioops.main run <message>\n"
        "  python -m bioops.main <message>\n\n"
        "Without arguments, BioOps starts an interactive local CLI.\n"
    )


def _interactive_loop() -> None:
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


def main() -> None:
    setup_logging()

    args = sys.argv[1:]

    if args and args[0] in {"-h", "--help"}:
        _print_help()
        return

    if not args or args[0] in {"chat", "interactive"}:
        _interactive_loop()
        return

    if args[0] in {"ask", "run"}:
        args = args[1:]

    message = " ".join(args).strip()
    if not message:
        _print_help()
        return

    print(run_message(message))


if __name__ == "__main__":
    main()

