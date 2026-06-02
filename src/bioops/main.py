from bioops.logging_config import setup_logging
from bioops.graph_orchestrator import LangGraphOrchestrator


def main() -> None:
    setup_logging()

    orchestrator = LangGraphOrchestrator()
    print("BioOps CLI started. Type 'exit' to quit.")

    while True:
        message = input("You: ")

        if message.lower() in {"exit", "quit"}:
            print("BioOps stopped.")
            break

        response = orchestrator.route(message)
        print(f"BioOps: {response}")


if __name__ == "__main__":
    main()