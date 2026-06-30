from bioops.logging_config import setup_logging
from bioops.graph_orchestrator import run_graph


def main() -> None:
    setup_logging()
    print("BioOps CLI started. Type 'exit' to quit.")

    while True:
        message = input("You: ")

        if message.lower() in {"exit", "quit"}:
            print("Goodbye")
            break

        response = run_graph(message)
        print(f"BioOps: {response}")


if __name__ == "__main__":
    main()
