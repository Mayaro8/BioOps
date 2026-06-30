import logging
from pathlib import Path
from typing import Optional

import typer

from logger_config import setup_logging
from argo import ArgoClient
from utils import load_config

app = typer.Typer(add_completion=False)
logger = logging.getLogger(__name__)


@app.command()
def main(
    config: Path = typer.Option(
        ..., 
        help="Path to the JSON file with workflow-parameters",
        exists=True,
        dir_okay=False,
        resolve_path=True
    ),
    debug_mode: Optional[bool] = typer.Option(
        False, 
        help="Enable detailed logging"
    ),
    contour: Optional[str] = typer.Option(
        "prod", 
        help="prod or dev"
    )
):
    """
    Run pipeline-v3.0 with configuration from the JSON file.
    """

    workflows = load_config(config)

    setup_logging(debug_mode=debug_mode) 
    

    for workflow in workflows:
        delay_config = workflow.get("delay_config", {})
        # Convert all delay_config values to integers
        if delay_config:
            delay_config = {k: int(v) for k, v in delay_config.items()}
        
        client = ArgoClient(
            k8s_cluster_name=workflow.get("k8s_cluster_name"),
            namespace=workflow.get("namespace", "default"),
            contour=contour,
            only_good=workflow.get('only_good', False),
            delay_config=delay_config
        )

        try:
            submit_method = getattr(client, workflow['submit_method'])

            excluded_keys = {
                "k8s_cluster_name", 
                "submit_method", 
                "namespace", 
                "debug_mode", 
                "only_good",
                "delay_config"
            }
            workflow_params = {
                k: v for k, v in workflow.items()
                if k not in excluded_keys
            }
            
            # Convert string boolean values to actual booleans
            if "wait" in workflow_params:
                wait_value = workflow_params["wait"]
                if isinstance(wait_value, str):
                    workflow_params["wait"] = wait_value.lower() in ("true", "yes", "1")

            submit_method(**workflow_params)

        except AttributeError:
                
            error_msg = f"Unknown method: {workflow['submit_method']}"
            logger.error(error_msg, exc_info=True)  
            raise typer.BadParameter(f"{workflow['submit_method']}")
    else:
        logger.info("All workflows submitted")

if __name__ == "__main__":
    app()
