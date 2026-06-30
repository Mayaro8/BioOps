from pathlib import Path
from typing import List, Dict, Any
import json

import typer

from dto import DelayConfig

def generate_delays_for_samples(
        samples: List[Dict[str, Any]],
        delay_config: DelayConfig
    ) -> None:
    counter = 0
    delay = delay_config.delay

    for sample in samples:
        if counter % delay_config.chunk_size == 0 and counter != 0:
             delay += delay_config.step
        counter += 1
        sample["delay"] = delay

def load_config(config_path: Path) -> List[Dict[str, Any]]:
    """Loads and validates the workflow configuration json-file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON format in the file: {config_path}\n{e}")
    
    if not isinstance(config, list):
        raise typer.BadParameter("The config file must contain a list of workflow dictionaries.")
    
    return config
