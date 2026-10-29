"""Tests for the pipeline agent's tools and guardrails, against a fake Airflow.

These check the code's rules (guards, approval, audit log, error handling), not the model's
judgment, so they need no API key, cost nothing, and run in seconds:
    pytest tests/
"""

import builtins
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import pipeline_agent as pa  # type: ignore # noqa: E402

RUN_ID = "manual__2026-10-22T09:00:00+00:00"


# ------------------------------------------------------------ a fake Airflow


class FakeAirflow(BaseHTTPRequestHandler):
    """Answers the same API calls as Airflow 3, from a dictionary the test controls."""

    state: dict = {}

    def log_message(self, *args):  # keep test output quiet
        pass

    def send_json(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        body = self.read_body()
        if self.path == "/auth/token":
            return self.send_json(201, {"access_token": "test-token"})
        self.state["writes"].append(("POST", self.path, body))
        if self.path.endswith("/dagRuns"):
            return self.send_json(200, {"dag_run_id": "manual__new", "state": "queued"})
        return self.send_json(200, {"total_entries": 1})

    def do_PATCH(self):
        body = self.read_body()
        dag_id = self.path.split("/")[4]
        self.state["writes"].append(("PATCH", self.path, body))
        self.state["paused"][dag_id] = body["is_paused"]
        self.send_json(200, {"dag_id": dag_id, "is_paused": body["is_paused"]})

    def do_GET(self):
        path = self.path.split("?")[0]
        parts = path.split("/")
        if "/logs/" in path:
            if self.headers.get("Accept") == "text/plain":
                return self.send_json(
                    406, {"detail": "Not Acceptable"}
                )  # what real Airflow 3 does
            return self.send_json(200, {"content": self.state["log"]})
        if path.endswith("/taskInstances"):
            return self.send_json(200, {"task_instances": self.state["tasks"]})
        if path.endswith("/dagRuns"):
            dag_id = parts[4]
            return self.send_json(
                200,
                {
                    "dag_runs": [
                        {"dag_run_id": RUN_ID, "state": self.state["run_state"][dag_id]}
                    ]
                },
            )
        if len(parts) == 5:  # /api/v2/dags/<dag_id>
            return self.send_json(
                200, {"dag_id": parts[4], "is_paused": self.state["paused"][parts[4]]}
            )
        return self.send_json(404, {"detail": "not found"})


@pytest.fixture
def airflow(monkeypatch, tmp_path):
    """Start a fake Airflow on a free port, point the agent at it, and give each test its own audit log."""
    FakeAirflow.state = {
        "paused": {"nba_clutch_pipeline": False, "nba_clutch_shots": False},
        "run_state": {"nba_clutch_pipeline": "failed", "nba_clutch_shots": "success"},
        "tasks": [
            {
                "task_id": "run_extract",
                "state": "failed",
                "try_number": 1,
                "duration": 30.0,
            }
        ],
        "log": [
            {
                "timestamp": "2026-10-22T09:00:00Z",
                "level": "info",
                "event": "2004-05 file already there",
            },
            {
                "timestamp": "2026-10-22T09:00:01Z",
                "level": "info",
                "event": "Pulling 2005-06 now",
            },
            {
                "timestamp": "2026-10-22T09:00:02Z",
                "level": "error",
                "event": "requests.exceptions.ReadTimeout: read timed out",
            },
        ],
        "writes": [],
    }
    server = HTTPServer(("127.0.0.1", 0), FakeAirflow)  # port 0 = any free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(pa, "AIRFLOW_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(pa.airflow, "token", None)
    monkeypatch.setattr(pa, "AUDIT_LOG", tmp_path / "audit.jsonl")
    yield FakeAirflow.state
    server.shutdown()


def answer_prompt(monkeypatch, reply):
    """Type `reply` at the approval prompt, and record whether the prompt was shown at all."""
    asked = []

    def fake_input(prompt=""):
        asked.append(prompt)
        if reply is EOFError:
            raise EOFError
        return reply

    monkeypatch.setattr(builtins, "input", fake_input)
    return asked


def audit_events():
    if not pa.AUDIT_LOG.exists():
        return []
    return [json.loads(line)["event"] for line in pa.AUDIT_LOG.read_text().splitlines()]


# ------------------------------------------------------------- read tools


def test_status_marks_paused_dags(airflow):
    airflow["paused"]["nba_clutch_shots"] = True
    status = pa.pipeline_status()
    assert "nba_clutch_shots (PAUSED" in status
    assert "nba_clutch_pipeline (PAUSED" not in status
    assert "run_extract: failed" in status


def test_task_log_reads_json_and_counts_cache_use(airflow):
    log = pa.task_log("nba_clutch_pipeline", RUN_ID, "run_extract")
    assert "1 files read from the cache, 1 pulled from the NBA API" in log
    assert "ReadTimeout" in log  # error lines survive the trimming


def test_airflow_down_gives_a_message_not_a_crash(airflow, monkeypatch):
    monkeypatch.setattr(pa, "AIRFLOW_URL", "http://127.0.0.1:1")
    assert pa.run_tool("pipeline_status", {}).startswith("Can't reach Airflow")


# ---------------------------------------------------------- trigger_pipeline


def test_trigger_needs_approval_and_is_logged(airflow, monkeypatch):
    asked = answer_prompt(monkeypatch, "y")
    result = pa.trigger_pipeline("test run")
    assert asked, "the operator was never asked"
    assert result.startswith("Triggered")
    assert (
        "POST",
        "/api/v2/dags/nba_clutch_pipeline/dagRuns",
        {"logical_date": None},
    ) in airflow["writes"]
    assert audit_events() == ["trigger_proposed", "trigger_done"]


@pytest.mark.parametrize("reply", ["n", "", "maybe", EOFError])
def test_anything_but_yes_is_no(airflow, monkeypatch, reply):
    answer_prompt(monkeypatch, reply)
    assert pa.trigger_pipeline("test run").startswith("Declined")
    assert airflow["writes"] == []
    assert audit_events() == ["trigger_proposed", "trigger_declined"]


def test_trigger_refused_during_an_active_run_without_asking(airflow, monkeypatch):
    airflow["run_state"]["nba_clutch_pipeline"] = "running"
    asked = answer_prompt(monkeypatch, "y")
    assert pa.trigger_pipeline("test run").startswith(
        "Refused: a run is already active"
    )
    assert asked == [] and airflow["writes"] == []


def test_trigger_refused_while_a_dag_is_paused(airflow, monkeypatch):
    airflow["paused"]["nba_clutch_shots"] = True
    asked = answer_prompt(monkeypatch, "y")
    assert "nba_clutch_shots is paused" in pa.trigger_pipeline("test run")
    assert asked == [] and airflow["writes"] == []


# ------------------------------------------------------- retry_failed_task


def test_retry_only_once_per_task(airflow, monkeypatch):
    answer_prompt(monkeypatch, "y")
    first = pa.retry_failed_task(
        "nba_clutch_pipeline", RUN_ID, "run_extract", "transient timeout"
    )
    assert first.startswith("Cleared")
    asked = answer_prompt(monkeypatch, "y")
    second = pa.retry_failed_task(
        "nba_clutch_pipeline", RUN_ID, "run_extract", "transient timeout"
    )
    assert second.startswith("Refused") and "already retried" in second
    assert asked == []  # refused before the prompt
    assert len(airflow["writes"]) == 1


def test_retry_refused_for_an_unknown_dag(airflow, monkeypatch):
    asked = answer_prompt(monkeypatch, "y")
    assert pa.retry_failed_task("someone_elses_dag", RUN_ID, "task", "x").startswith(
        "Refused"
    )
    assert asked == [] and airflow["writes"] == []


# ----------------------------------------------------------- set_dag_paused


def test_unpause_needs_approval(airflow, monkeypatch):
    airflow["paused"]["nba_clutch_pipeline"] = True
    answer_prompt(monkeypatch, "y")
    assert pa.set_dag_paused(
        "nba_clutch_pipeline", False, "run stuck in queued"
    ).endswith("unpaused.")
    assert airflow["paused"]["nba_clutch_pipeline"] is False
    assert audit_events() == ["pause_change_proposed", "pause_change_done"]


def test_pause_change_is_a_no_op_when_already_in_that_state(airflow, monkeypatch):
    asked = answer_prompt(monkeypatch, "y")
    assert "already unpaused" in pa.set_dag_paused("nba_clutch_pipeline", False, "x")
    assert asked == [] and airflow["writes"] == []


# ------------------------------------------------------------ diagnose-only


def test_diagnose_only_never_offers_action_tools(monkeypatch):
    """The model is never told the action tools exist; checked without calling Claude."""
    offered = []

    class FakeMessages:
        def create(self, **kwargs):
            offered.append({tool["name"] for tool in kwargs["tools"]})
            return type("Response", (), {"stop_reason": "end_turn", "content": []})()

    monkeypatch.setattr(
        pa.anthropic,
        "Anthropic",
        lambda: type("Client", (), {"messages": FakeMessages()})(),
    )
    pa.ask("Retry the failed task.", allow_actions=False)
    pa.ask("Retry the failed task.", allow_actions=True)
    assert offered[0].isdisjoint(
        {"trigger_pipeline", "retry_failed_task", "set_dag_paused"}
    )
    assert {"trigger_pipeline", "retry_failed_task", "set_dag_paused"} <= offered[1]
