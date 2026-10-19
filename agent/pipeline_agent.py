"""Pipeline agent: checks on the Airflow pipeline, diagnoses failures, and (with your approval) acts.

The agent never runs the pipeline itself. Airflow does. The agent works through Airflow's REST API,
the same way you would in the Airflow UI: reading run states and logs, and, only after you type "y",
triggering a run or retrying a failed task.

Usage (from the project root, with Airflow running in Docker):
    python3 agent/pipeline_agent.py "How did the last pipeline run go?"
    python3 agent/pipeline_agent.py --diagnose-only "Why did the last run fail?"
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

import analyst  # the read-only database connection, reused for data_freshness

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "pipeline" / "cached_data"
FAILURES_DIR = CACHE_DIR / "failures"
AUDIT_LOG = ROOT / "agent" / "pipeline_audit.jsonl"

AIRFLOW_URL = os.environ.get("AIRFLOW_API_URL", "http://localhost:8080")
# The local Docker setup's default login (see the README); set these to use another account.
AIRFLOW_USER = os.environ.get("AIRFLOW_USERNAME", "airflow")
AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_PASSWORD", "airflow")

DAGS = ["nba_clutch_pipeline", "nba_clutch_shots"]
ACTIVE_STATES = {"queued", "running"}
MAX_RETRIES_PER_TASK = (
    1  # after one retry fails again, the agent stops and hands it to you
)
MAX_LOG_CHARS = 12_000
MAX_STEPS = 12
MAX_TOKENS = 4096
MODEL = analyst.MODEL

console = Console()
trace = Console(stderr=True)


# ------------------------------------------------------------ airflow api


class AirflowClient:
    """A thin wrapper around Airflow 3's REST API: one token, then plain GET and POST calls."""

    def __init__(self) -> None:
        self.token: str | None = None

    def _headers(self) -> dict:
        if self.token is None:
            response = requests.post(
                f"{AIRFLOW_URL}/auth/token",
                json={"username": AIRFLOW_USER, "password": AIRFLOW_PASSWORD},
                timeout=10,
            )
            response.raise_for_status()
            self.token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self.token}"}

    def get(
        self, path: str, params: dict | None = None, accept: str = "application/json"
    ) -> requests.Response:
        response = requests.get(
            f"{AIRFLOW_URL}/api/v2{path}",
            params=params,
            headers={**self._headers(), "Accept": accept},
            timeout=30,
        )
        response.raise_for_status()
        return response

    def post(self, path: str, body: dict) -> dict:
        response = requests.post(
            f"{AIRFLOW_URL}/api/v2{path}",
            json=body,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


airflow = AirflowClient()


def recent_runs(dag_id: str, limit: int) -> list[dict]:
    return airflow.get(
        f"/dags/{dag_id}/dagRuns", {"order_by": "-start_date", "limit": limit}
    ).json()["dag_runs"]


def task_instances(dag_id: str, run_id: str) -> list[dict]:
    return airflow.get(f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances").json()[
        "task_instances"
    ]


def active_runs() -> list[str]:
    """Every run of either DAG that is queued or running right now."""
    return [
        f"{dag_id} / {run['dag_run_id']} ({run['state']})"
        for dag_id in DAGS
        for run in recent_runs(dag_id, 5)
        if run["state"] in ACTIVE_STATES
    ]


# ---------------------------------------------------------------- audit log


def audit(event: str, **details) -> None:
    """Append one line to the audit log: every action the agent proposed, and what happened."""
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        **details,
    }
    with AUDIT_LOG.open("a") as log:
        log.write(json.dumps(record) + "\n")


def retries_already_done(dag_id: str, run_id: str, task_id: str) -> int:
    if not AUDIT_LOG.exists():
        return 0
    count = 0
    for line in AUDIT_LOG.read_text().splitlines():
        record = json.loads(line)
        if (
            record["event"],
            record.get("dag_id"),
            record.get("run_id"),
            record.get("task_id"),
        ) == (
            "retry_done",
            dag_id,
            run_id,
            task_id,
        ):
            count += 1
    return count


def approved(proposal: str) -> bool:
    """Ask the person at the terminal. Anything but y or yes is a no."""
    console.print(
        Panel(
            escape(proposal),
            title="[bold yellow]The agent wants to act[/]",
            border_style="yellow",
        )
    )
    try:
        return input("Approve? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:  # no one at the keyboard, for example when run from a script
        return False


# --------------------------------------------------------------- read tools


def pipeline_status() -> str:
    lines = []
    for dag_id in DAGS:
        runs = recent_runs(dag_id, 3)
        if not runs:
            lines.append(f"{dag_id}: no runs yet.")
            continue
        lines.append(f"{dag_id}:")
        for run in runs:
            lines.append(
                f"  run {run['dag_run_id']}: {run['state']} (started {run.get('start_date')}, ended {run.get('end_date')})"
            )
        latest = runs[0]
        for task in task_instances(dag_id, latest["dag_run_id"]):
            lines.append(
                f"    task {task['task_id']}: {task['state']} (try {task.get('try_number')}, "
                f"{task.get('duration') or 0:.0f}s)"
            )
    return "\n".join(lines)


def trim_log(text: str) -> str:
    """Keep what diagnosis needs: cache use, every error-looking line, plus the end of the log."""
    lines = text.splitlines()
    from_cache = sum("file already there" in line for line in lines)
    from_api = sum("Pulling " in line for line in lines)
    cache_line = f"Cache use in this log: {from_cache} files read from the cache, {from_api} pulled from the NBA API.\n\n"
    keywords = ("error", "exception", "traceback", "failed", "retrying", "warning")
    flagged = [line for line in lines if any(word in line.lower() for word in keywords)]
    tail = lines[-120:]
    trimmed = (
        cache_line
        + "Lines mentioning errors:\n"
        + "\n".join(flagged[-60:])
        + "\n\nEnd of the log:\n"
        + "\n".join(tail)
    )
    return trimmed[-MAX_LOG_CHARS:]


def log_text(content) -> str:
    """Airflow 3 returns a log as JSON: a list of structured entries. Turn it back into plain lines."""
    if isinstance(content, str):
        return content
    lines = []
    for entry in content or []:
        if isinstance(entry, dict):
            prefix = " ".join(
                str(entry[key]) for key in ("timestamp", "level") if entry.get(key)
            )
            lines.append(f"{prefix} {entry.get('event', '')}".strip())
            # Exceptions arrive as structured details rather than a printed traceback.
            for detail in entry.get("error_detail") or []:
                if isinstance(detail, dict):
                    lines.append(
                        f"{detail.get('exc_type', 'Error')}: {detail.get('exc_value', '')}"
                    )
        elif (
            isinstance(entry, (list, tuple)) and entry
        ):  # older format: [host, text] pairs
            lines.append(str(entry[-1]))
        else:
            lines.append(str(entry))
    return "\n".join(lines)


def task_log(
    dag_id: str, run_id: str, task_id: str, try_number: int | None = None
) -> str:
    if try_number is None:
        task = next(
            (t for t in task_instances(dag_id, run_id) if t["task_id"] == task_id), None
        )
        if task is None:
            return f"No task {task_id} in {dag_id} / {run_id}."
        try_number = max(task.get("try_number") or 1, 1)
    response = airflow.get(
        f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}",
        {"full_content": "true"},
    )
    return trim_log(log_text(response.json().get("content")))


def failure_manifests() -> str:
    """The extract step's record of API calls that still failed after retries."""
    if not FAILURES_DIR.exists() or not any(FAILURES_DIR.glob("*.json")):
        return "No failure manifests: every API call in the last extract succeeded (or no extract has run)."
    parts = []
    for path in sorted(FAILURES_DIR.glob("*.json")):
        failures = json.loads(path.read_text())
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            timespec="minutes"
        )
        parts.append(
            f"{path.name} ({len(failures)} failed calls, written {modified}):\n{json.dumps(failures[:10], indent=1)}"
        )
        if len(failures) > 10:
            parts.append(f"  ... and {len(failures) - 10} more")
    return "\n\n".join(parts)


def cache_status() -> str:
    """How much of the extract is already cached on disk, which decides whether a run takes minutes or hours."""
    if not CACHE_DIR.exists():
        return "No cache folder: a run would pull everything from the NBA API (about 3.5 hours)."
    lines = []
    for folder in sorted(
        p for p in CACHE_DIR.iterdir() if p.is_dir() and p.name != "failures"
    ):
        files = list(folder.rglob("*.parquet"))
        if not files:
            lines.append(f"{folder.name}: empty")
            continue
        newest = datetime.fromtimestamp(
            max(f.stat().st_mtime for f in files)
        ).isoformat(timespec="minutes")
        lines.append(f"{folder.name}: {len(files):,} cached files, newest {newest}")
    if not lines:
        return "The cache folder is empty: a run would pull everything from the NBA API (about 3.5 hours)."
    return "\n".join(lines)


def data_freshness() -> str:
    if not analyst.DB_PATH.exists():
        return "No database file yet: the pipeline has never finished a load."
    built = datetime.fromtimestamp(analyst.DB_PATH.stat().st_mtime).isoformat(
        timespec="minutes"
    )
    try:
        with analyst.connect() as con:
            seasons = con.execute(
                "SELECT COUNT(*), MIN(season), MAX(season) FROM player_clutch_performance"
            ).fetchone()
            shots = con.execute("SELECT COUNT(*) FROM shots_with_opponent").fetchone()[
                0
            ]
    except (
        Exception
    ) as error:  # usually the file is locked because a run is writing to it
        return f"Database last written {built}, but it can't be read right now: {error}"
    return (
        f"Database last written {built}. player_clutch_performance: {seasons[0]:,} player-seasons, "
        f"{seasons[1]} to {seasons[2]}. shots_with_opponent: {shots:,} clutch shots."
    )


# -------------------------------------------------------------- action tools


def guard_no_active_runs() -> str | None:
    running = active_runs()
    if running:
        return (
            "Refused: a run is already active, and DuckDB allows one writer at a time: "
            + "; ".join(running)
        )
    return None


def trigger_pipeline(reason: str) -> str:
    refusal = guard_no_active_runs()
    if refusal:
        return refusal
    audit("trigger_proposed", reason=reason)
    if not approved(f"Trigger a new run of nba_clutch_pipeline.\n\nReason: {reason}"):
        audit("trigger_declined", reason=reason)
        return "Declined by the operator. Nothing was triggered."
    run = airflow.post("/dags/nba_clutch_pipeline/dagRuns", {"logical_date": None})
    audit("trigger_done", reason=reason, run_id=run["dag_run_id"])
    return f"Triggered nba_clutch_pipeline run {run['dag_run_id']} (state: {run['state']})."


def retry_failed_task(dag_id: str, run_id: str, task_id: str, reason: str) -> str:
    if dag_id not in DAGS:
        return f"Refused: {dag_id} isn't one of this project's DAGs."
    done = retries_already_done(dag_id, run_id, task_id)
    if done >= MAX_RETRIES_PER_TASK:
        return (
            f"Refused: {task_id} in {run_id} was already retried {done} time(s). "
            "It failed again, so this needs a person to look at it."
        )
    refusal = guard_no_active_runs()
    if refusal:
        return refusal
    details = dict(dag_id=dag_id, run_id=run_id, task_id=task_id, reason=reason)
    audit("retry_proposed", **details)
    if not approved(
        f"Retry {task_id} (and the tasks after it) in {dag_id} / {run_id}.\n\nReason: {reason}"
    ):
        audit("retry_declined", **details)
        return "Declined by the operator. Nothing was retried."
    airflow.post(
        f"/dags/{dag_id}/clearTaskInstances",
        {
            "dry_run": False,
            "dag_run_id": run_id,
            "task_ids": [task_id],
            "only_failed": True,
            "include_downstream": True,
        },
    )
    audit("retry_done", **details)
    return f"Cleared {task_id} in {dag_id} / {run_id}; Airflow will rerun it and the tasks after it."


# ------------------------------------------------------- what Claude is told

READ_TOOLS = [
    {
        "name": "pipeline_status",
        "description": "The last 3 runs of both DAGs, with the state of every task in each DAG's latest run. Call this first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "task_log",
        "description": "The log of one task try, trimmed to error lines plus the end of the log. Read this before diagnosing any failure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dag_id": {"type": "string", "enum": DAGS},
                "run_id": {"type": "string"},
                "task_id": {"type": "string"},
                "try_number": {
                    "type": "integer",
                    "description": "Omit to get the latest try.",
                },
            },
            "required": ["dag_id", "run_id", "task_id"],
        },
    },
    {
        "name": "failure_manifests",
        "description": "NBA API calls that still failed after the extract step's retries, written to disk by the pipeline.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cache_status",
        "description": "How many API responses are already cached on disk, per data type. A warm cache makes a run fast; an empty one means a roughly 3.5-hour pull.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "data_freshness",
        "description": "When the database was last written, and row counts of the main analysis tables.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

ACTION_TOOLS = [
    {
        "name": "trigger_pipeline",
        "description": "Start a new full pipeline run. The operator must approve it. Refused if any run is active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why a run is needed, for the operator and the audit log.",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "retry_failed_task",
        "description": (
            "Clear one failed task so Airflow reruns it and the tasks after it. The operator must approve it. "
            f"Only {MAX_RETRIES_PER_TASK} retry per task per run; refused if any run is active."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dag_id": {"type": "string", "enum": DAGS},
                "run_id": {"type": "string"},
                "task_id": {"type": "string"},
                "reason": {
                    "type": "string",
                    "description": "The diagnosis that makes a retry worthwhile.",
                },
            },
            "required": ["dag_id", "run_id", "task_id", "reason"],
        },
    },
]

SYSTEM_PROMPT = """You are the on-call assistant for an NBA data pipeline orchestrated by Airflow.

How the pipeline works:
- DAG nba_clutch_pipeline: run_extract (pulls NBA API data and loads DuckDB) -> run_dbt_deps -> run_dbt (builds and tests
  everything except shot models) -> trigger_shots, which starts DAG nba_clutch_shots.
- DAG nba_clutch_shots: run_load_shots (pulls clutch shots for qualifying player-seasons) -> run_dbt (full build and tests).
- A fresh run takes about 3.5 hours; reruns read a local cache and are much faster.
- DuckDB allows one writer at a time, so two runs must never overlap.
- The extract retries failed API calls with backoff. Calls that still fail are written to failure manifests, and the run
  stops on purpose so incomplete data never reaches dbt. Successful calls stay cached, so a rerun only refetches what failed.

How to work:
- Call pipeline_status first. Read a task's log before saying why it failed; never guess from the task name.
- Classify every failure as one of: transient (API timeouts, throttling, connection errors), data (a dbt test failed:
  the data broke an assumption), code (an exception from a bug), or unknown. Quote the log lines that support it.
- A retry only makes sense for transient failures. For data or code failures, explain what a person should look at.
- Never retry the same task more than once; if it failed after a retry, stop and hand it to the operator.
- Before proposing trigger_pipeline, call cache_status and say roughly how long the run should take: a warm cache means
  most data is read from disk; an empty or missing cache means a full pull of about 3.5 hours.
- task_log reports how many files a run read from the cache versus pulled from the API; use it to confirm a run used the cache.
- Only propose an action when the evidence supports it, and state the reason clearly: the operator reads it before approving.
- If action tools aren't available to you, say what action you would recommend instead.
- End with a short summary: what happened, your diagnosis, and what was done or should be done next."""


def run_tool(name: str, tool_input: dict) -> str:
    tools = {
        "pipeline_status": pipeline_status,
        "task_log": task_log,
        "failure_manifests": failure_manifests,
        "data_freshness": data_freshness,
        "cache_status": cache_status,
        "trigger_pipeline": trigger_pipeline,
        "retry_failed_task": retry_failed_task,
    }
    if name not in tools:
        return f"Unknown tool: {name}"
    try:
        return tools[name](**tool_input)
    except requests.ConnectionError:
        return f"Can't reach Airflow at {AIRFLOW_URL}. Is the Docker stack running (docker compose up -d)?"
    except requests.HTTPError as error:
        return f"Airflow API error: {error.response.status_code} {error.response.text[:300]}"


def show_tool_call(step: int, name: str, tool_input: dict, output: str) -> None:
    colour = "yellow" if name in {"trigger_pipeline", "retry_failed_task"} else "cyan"
    arguments = ", ".join(
        f"{key}={value}" for key, value in tool_input.items() if key != "reason"
    )
    trace.print(
        f"\n[bold {colour}]Step {step}[/] [{colour}]{name}[/] [dim]{escape(arguments)}[/]"
    )
    first_line = output.splitlines()[0] if output else ""
    trace.print(f"  [dim]{escape(first_line[:160])}[/]")


# ------------------------------------------------------------------ the loop


def ask(question: str, allow_actions: bool = True) -> str:
    client = anthropic.Anthropic()
    tools = READ_TOOLS + (ACTION_TOOLS if allow_actions else [])
    system = SYSTEM_PROMPT + (
        ""
        if allow_actions
        else "\n\nYou are in diagnose-only mode: no action tools are available."
    )
    messages = [{"role": "user", "content": question}]
    started = time.perf_counter()

    for step in range(1, MAX_STEPS + 1):
        with trace.status("[dim]Thinking…[/]", spinner="dots"):
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
            )
        messages.append({"role": "assistant", "content": response.content})
        text = "".join(block.text for block in response.content if block.type == "text")

        if response.stop_reason != "tool_use":
            trace.print(
                f"\n[dim]{step} steps · {time.perf_counter() - started:.1f}s · stop reason: {response.stop_reason}[/]"
            )
            if response.stop_reason == "max_tokens":
                text += "\n\n_(This answer was cut off at the output limit.)_"
            return text

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output = run_tool(block.name, block.input)
            show_tool_call(step, block.name, block.input, output)
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": output}
            )
        messages.append({"role": "user", "content": results})

    return f"Stopped after {MAX_STEPS} steps without finishing. Check the trace above."


def write_report(path: Path, question: str, answer: str) -> None:
    """Save the agent's report as Markdown, for runs with no one watching (like Airflow's failure callback)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    written = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(
        f"# Pipeline agent report\n\n_Written {written}_\n\n**Question:** {question}\n\n{answer}\n"
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    diagnose_only = "--diagnose-only" in args
    args = [arg for arg in args if arg != "--diagnose-only"]
    report_path = None
    if "--report" in args:
        at = args.index("--report")
        report_path = Path(args[at + 1])
        del args[at : at + 2]
    if len(args) != 1:
        sys.exit(
            'Usage: python3 agent/pipeline_agent.py [--diagnose-only] [--report FILE] "your question"'
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY isn't set, so the agent can't run.")

    mode = "diagnose only" if diagnose_only else "can act, with your approval"
    console.print(
        Panel(
            escape(args[0]),
            title=f"[bold]Pipeline agent[/] [dim]({mode})[/]",
            border_style="cyan",
        )
    )
    answer = ask(args[0], allow_actions=not diagnose_only)
    console.print(
        Panel(
            Markdown(answer),
            title="[bold]Report[/]",
            border_style="green",
            padding=(1, 2),
        )
    )
    if report_path:
        write_report(report_path, args[0], answer)
        console.print(f"[dim]Report saved to {report_path}[/]")
