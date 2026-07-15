import argparse
import requests

from bioops.tools.submit_master_scope import SubmitMasterScopeMonitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--dialog-id", required=True)
    parser.add_argument("--namespace", default="argo")
    parser.add_argument("--workflow-prefix", default="bioops-submit-master")
    parser.add_argument("--workflow-template", default="bioops-submit-master-local")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--sample-id", default="")
    parser.add_argument("--workflow-name", default="")
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()

    monitor = SubmitMasterScopeMonitor(
        namespace=args.namespace,
        workflow_name_prefix=args.workflow_prefix,
        workflow_template_name=args.workflow_template,
    )

    if args.workflow_name:
        report = monitor.render_workflow_status(args.workflow_name)
    elif args.sample_id:
        report = monitor.render_sample_status(
            args.sample_id, args.batch_id or None
        )
    elif args.batch_id:
        report = monitor.render_batch_status(args.batch_id)
    elif args.latest:
        report = monitor.render_latest_progress()
    else:
        raise SystemExit(
            "D3 requires --batch-id, --sample-id, "
            "--workflow-name, or --latest."
        )

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
