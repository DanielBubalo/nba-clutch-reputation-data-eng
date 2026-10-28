"""The main DAG's schedule: off by default, and never on the presentation database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "airflow" / "dags"))
from pipeline_schedule import PRESENTATION_DB, pipeline_schedule  # type: ignore # noqa: E402

LIVE_DB = "/opt/airflow/project/live/nba_clutch_live.duckdb"
DAILY = "0 14 * * *"


def test_no_schedule_set_means_manual_only():
    assert pipeline_schedule({"NBA_DB_PATH": LIVE_DB}) is None


def test_blank_schedule_means_manual_only():
    assert (
        pipeline_schedule({"NBA_DB_PATH": LIVE_DB, "NBA_PIPELINE_SCHEDULE": "  "})
        is None
    )


def test_schedule_runs_on_the_live_database():
    assert (
        pipeline_schedule({"NBA_DB_PATH": LIVE_DB, "NBA_PIPELINE_SCHEDULE": DAILY})
        == DAILY
    )


def test_schedule_is_ignored_on_the_presentation_database():
    assert (
        pipeline_schedule(
            {"NBA_DB_PATH": PRESENTATION_DB, "NBA_PIPELINE_SCHEDULE": DAILY}
        )
        is None
    )


def test_no_database_setting_counts_as_the_presentation_database():
    assert pipeline_schedule({"NBA_PIPELINE_SCHEDULE": DAILY}) is None
