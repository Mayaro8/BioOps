#!/usr/bin/env python3
"""
Dry run version of main.py
This script reads config.json and shows what argo commands would be executed
Usage: python dry_main.py --config <config.json> [--contour prod|dev]
"""

import logging
from pathlib import Path
from typing import Optional

import typer

from logger_config import setup_logging
from dry_argo import DryArgoClient
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
    Dry run: Show what argo commands would be executed from the config file.
    """
    
    workflows = load_config(config)
    
    setup_logging(debug_mode=debug_mode)
    
    print("=== DRY RUN MODE - Showing commands that would be executed ===\n")
    
    for workflow in workflows:
        delay_config = workflow.get("delay_config", {})
        # Convert all delay_config values to integers - same as main.py
        if delay_config:
            delay_config = {k: int(v) for k, v in delay_config.items()}
        
        submit_method_name = workflow.get("submit_method")
        
        # Only support HLA for now
        if submit_method_name != "submit_hla":
            logger.warning(f"Skipping {submit_method_name} - only submit_hla is supported in dry run mode")
            continue
        
        client = DryArgoClient(
            namespace=workflow.get("namespace", "default"),
            contour=contour,
            only_good=workflow.get('only_good', False),
            delay_config=delay_config
        )
        
        try:
            submit_method = getattr(client, submit_method_name)
            
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
            
            # Convert string boolean values to actual booleans - same as main.py
            if "wait" in workflow_params:
                wait_value = workflow_params["wait"]
                if isinstance(wait_value, str):
                    workflow_params["wait"] = wait_value.lower() in ("true", "yes", "1")
            
            print(f"\n--- Workflow: {submit_method_name} ---")
            submit_method(**workflow_params)
            
        except AttributeError:
            error_msg = f"Unknown method: {workflow['submit_method']}"
            logger.error(error_msg, exc_info=True)
            raise typer.BadParameter(f"{workflow['submit_method']}")
    
    print("\n=== Dry run complete ===")

if __name__ == "__main__":
    app()

