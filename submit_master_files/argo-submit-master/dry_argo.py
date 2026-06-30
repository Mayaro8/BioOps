#!/usr/bin/env python3
"""
Dry run version of argo.py - only for HLA
This script mimics how argo.py calls argo_submit.sh but with --dry-run flag
"""

import subprocess
import json
import os
from pathlib import Path
from typing import List, Dict

from dto import DelayConfig
from utils import generate_delays_for_samples

class DryArgoClient:
    """Dry run version of ArgoClient - only implements HLA submit"""
    
    def __init__(
        self,
        contour: str,
        only_good: bool,
        delay_config: Dict,
        namespace: str = "default",
    ):
        self.namespace = namespace
        self.contour = contour
        self.only_good = only_good
        self.delay_config = delay_config

    def _validate_samples(
        self,
        delay_config: Dict,
        sample_ids: List[Dict[str, str]],
        contour: str,
        only_good: bool,
    ):
        """Validate samples and add delays - same as argo.py"""
        delay_config_dto = DelayConfig(**delay_config)
        if not sample_ids:
            # In real version, this would call get_data_from_mongo
            pass
        generate_delays_for_samples(sample_ids, delay_config_dto)

    def _call_argo_submit_script(
        self,
        submit_function_name: str,
        env_vars: Dict[str, str],
        wait: bool = True,
    ):
        """Calls argo_submit.sh with --dry-run flag to show the command"""
        script_dir = Path(__file__).parent
        script_path = script_dir / "argo_submit.sh"
        
        if not script_path.exists():
            raise FileNotFoundError(f"argo_submit.sh not found at {script_path}")
        
        # Prepare environment variables - same as argo.py
        env = os.environ.copy()
        env.update({
            "NAMESPACE": self.namespace,
            "WAIT": "true" if wait else "false",
            "STOP_ON_ERROR": "false",
            "DRY_RUN": "true",  # Enable dry-run mode
        })
        
        # Convert env_vars values to strings and handle special cases - same as argo.py
        for key, value in env_vars.items():
            if value is None:
                env[key] = ""
            elif isinstance(value, (dict, list)):
                env[key] = json.dumps(value)
            else:
                env[key] = str(value)
        
        # Build command to call the script with --dry-run
        command = [str(script_path), submit_function_name, "--dry-run"]
        if not wait:
            command.append("--no-wait")
        
        # Execute and capture output
        result = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=os.sys.stderr)
        
        return result

    def submit_hla(
        self,
        local_input_hla: str,
        sample_ids: List[Dict[str, str]],
        basename: str,
        input_hla_s3: str,
        output_hla_s3: str,
        mnt_bucket_hla: str,
        reference: str,
        env: str,
        wait: bool = True,
    ):
        """Dry run for HLA submit - same flow as argo.py"""
        
        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )
        
        env_vars = {
            "SAMPLE_IDS": sample_ids,
            "LOCAL_INPUT_HLA": local_input_hla,
            "BASENAME": basename,
            "INPUT_HLA_S3": input_hla_s3,
            "OUTPUT_HLA_S3": output_hla_s3,
            "MNT_BUCKET_HLA": mnt_bucket_hla,
            "REFERENCE": reference,
            "ENV": env,
        }
        self._call_argo_submit_script("submit_hla", env_vars, wait)
