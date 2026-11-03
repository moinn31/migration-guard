import os
import sys
import json
import logging
import shutil
import tempfile
from pathlib import Path
import urllib.request
import urllib.parse
from git import Repo

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("migration-worker")

JOB_ID = os.environ.get("JOB_ID")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
JOB_TOKEN = os.environ.get("JOB_TOKEN", "")

def update_progress(status: str, message: str, node_analysis: dict = None):
    try:
        url = f"{BACKEND_URL}/internal/jobs/{JOB_ID}/progress"
        payload = json.dumps({"status": status, "message": message, "node_analysis": node_analysis}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {JOB_TOKEN}"}, method="PATCH")
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception as e:
        logger.warning(f"Failed to post progress: {e}")

def main():
    if not JOB_ID:
        logger.error("Missing JOB_ID environment variable.")
        sys.exit(1)

    logger.info(f"Starting Azure worker execution for job_id={JOB_ID}")
    update_progress("STARTING", "Worker container initialized. Preparing execution environment...")

    # For manual test/run:
    logger.info("Worker execution completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
