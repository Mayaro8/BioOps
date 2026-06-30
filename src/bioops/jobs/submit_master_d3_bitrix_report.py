import argparse
import requests

from bioops.tools.argo_workflow_monitor import ArgoWorkflowMonitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--dialog-id", required=True)
    parser.add_argument("--namespace", default="argo")
    parser.add_argument("--workflow-prefix", default="bioops-submit-master")
    parser.add_argument("--workflow-template", default="bioops-submit-master-local")
    args = parser.parse_args()

    monitor = ArgoWorkflowMonitor(
        namespace=args.namespace,
        workflow_name_prefix=args.workflow_prefix,
        workflow_template_name=args.workflow_template,
    )

    report = monitor.render_latest_progress()

    print("=== D3 report ===")
    print(report)

    bitrix_url = args.webhook_url.rstrip("/") + "/im.message.add.json"

    message = "[B]BioOps D3 SubmitMaster Report[/B]\n\n" + report

    response = requests.post(
        bitrix_url,
        data={
            "DIALOG_ID": args.dialog_id,
            "MESSAGE": message,
        },
        timeout=15,
    )

    print("=== Bitrix response ===")
    print("status_code:", response.status_code)
    print(response.text)

    response.raise_for_status()


if __name__ == "__main__":
    main()
