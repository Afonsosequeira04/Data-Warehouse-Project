"""
Airflow notification utilities.

Provides a `notify(context, status)` function that:
- Sends a Slack message if SLACK_WEBHOOK_URL is set.
- Otherwise logs a warning and does not fail the DAG.

The `status` argument should be either "success" or "failure".
"""

import json
import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


def notify(context: Dict[str, Any], status: str) -> None:
    """
    Send a notification about a DAG run status.

    Args:
        context: The Airflow context dictionary (contains dag, task, execution_date, etc.)
        status: Either "success" or "failure"
    """
    dag_id = context.get("dag", {}).dag_id if context.get("dag") else "unknown"
    task_id = context.get("task_instance", {}).task_id if context.get("task_instance") else "unknown"
    execution_date = context.get("execution_date")
    log_url = context.get("task_instance", {}).log_url if context.get("task_instance") else "N/A"

    if status == "failure":
        title = f"🔴 DAG Failed: {dag_id}"
        message = (
            f"*Task:* {task_id}\n"
            f"*Execution Date:* {execution_date}\n"
            f"*Log URL:* {log_url}\n"
        )
        # Add extra warning if a staging test failed
        if "staging" in task_id.lower() and "test" in task_id.lower():
            message += (
                "\n⚠️ *Staging test failed.* The marts layer is now unavailable "
                "until the next successful DAG run (staging tables are rebuilt, "
                "which cascades drops the marts views)."
            )
    else:
        title = f"🟢 DAG Succeeded: {dag_id}"
        message = (
            f"*Execution Date:* {execution_date}\n"
            f"All tasks completed successfully."
        )

    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook_url:
        payload = {"text": f"{title}\n{message}"}
        try:
            response = requests.post(slack_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Slack notification sent for %s (%s)", dag_id, status)
        except Exception as e:
            logger.error("Failed to send Slack notification: %s", e)
    else:
        # No Slack webhook configured — log a warning and continue
        logger.warning(
            "No SLACK_WEBHOOK_URL configured; notification for %s (%s) would be: %s",
            dag_id, status, message
        )


def on_failure_callback(context: Dict[str, Any]) -> None:
    """Airflow on_failure_callback hook."""
    notify(context, "failure")


def on_success_callback(**context: Any) -> None:
    """Airflow on_success_callback hook (for final task)."""
    notify(context, "success")