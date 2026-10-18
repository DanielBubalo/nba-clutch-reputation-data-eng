"""Airflow failure callback: when a task fails, the pipeline agent diagnoses it and writes a report.

The agent runs in diagnose-only mode, so it has no action tools: it can read run states, logs and
failure manifests, but it can't retry or trigger anything. A person reads the report and decides.
Reports land in agent/reports/ in the project folder.
"""

import logging
import os
import re
import subprocess
from pathlib import Path

PROJECT = Path(os.environ.get("NBA_PROJECT_DIR", "/opt/airflow/project"))
AGENT = PROJECT / "agent" / "pipeline_agent.py"
REPORTS = PROJECT / "agent" / "reports"
TIMEOUT_SECONDS = 600

log = logging.getLogger(__name__)


def diagnose_failure(context: dict) -> None:
    """Run the pipeline agent on the task that just failed. Never raises: a broken callback mustn't hide the failure."""
    try:
        ti = context["ti"]
        dag_id, task_id, run_id = ti.dag_id, ti.task_id, ti.run_id
        try_number = getattr(ti, "try_number", None)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            log.warning(
                "Pipeline agent skipped: ANTHROPIC_API_KEY isn't set in the Airflow containers."
            )
            return

        safe_run = re.sub(r"[^A-Za-z0-9_-]+", "-", run_id)
        report = REPORTS / f"{dag_id}__{task_id}__{safe_run}__try{try_number}.md"
        question = (
            f"Task {task_id} in DAG {dag_id} just failed (run {run_id}, try {try_number}). "
            "Read its log, classify the failure, and say what a person should do next."
        )
        log.info(
            "Asking the pipeline agent to diagnose %s / %s / %s",
            dag_id,
            run_id,
            task_id,
        )
        result = subprocess.run(
            [
                "python3",
                "-u",
                str(AGENT),
                "--diagnose-only",
                "--report",
                str(report),
                question,
            ],
            cwd=PROJECT,
            timeout=TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            log.info("Pipeline agent report written to %s", report)
        else:
            # Still leave a report, so the failure doesn't go unexplained just because the agent couldn't run.
            REPORTS.mkdir(parents=True, exist_ok=True)
            report.write_text(
                f"# Pipeline agent couldn't diagnose this failure\n\n{question}\n\n"
                f"The agent exited with code {result.returncode}. The end of its output:\n\n"
                f"```\n{result.stderr[-3000:]}\n```\n"
            )
            log.warning(
                "Pipeline agent exited with %s; details in %s",
                result.returncode,
                report,
            )
    except (
        Exception
    ):  # the callback is a helper; the task's own failure is what matters
        log.exception("Pipeline agent callback failed")
