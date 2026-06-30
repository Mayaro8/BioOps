import json
import os
import subprocess
import logging
from typing import Dict, Any, List

import typer
MONGO_YF_ID = os.environ.get("MONGO_YF_ID", "d4ehfm7m9hk2id8t149f")

def get_data_from_mongo(
        batch_id: str,
        contour: str, 
        only_good: bool
    ) -> List[Dict[str, Any]]:
    logger = logging.getLogger('MongoDataFetching')
    logger.debug("Executing command: get_data_from_mongo")

    if contour == "prod":
        db_name = "datastore"
    else:
        db_name = "datastore-test"

    query = {"batch_id": batch_id}

    if only_good:
        query["good"] = True

    request_body = {"queryStringParameters":
            {"cluster_name":"datastore",
             "db_name": db_name,
             "collection_name": "status",
             "query": query,
             "projection": {"_id": False, "batch_id": False, "good": False}
            }
    }
    request_json = json.dumps(request_body)

    command = ["yc", "serverless", "function", "invoke", f"{MONGO_YF_ID}", "-d", request_json]
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
        )
        logger.debug(f"Command executed successfully. Standard output: {result.stdout}")
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"{e.stderr}")
        typer.secho(f"Сommand failed or terminated.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

