"""When the main DAG runs on its own. Kept apart from the DAG file so it can be tested without Airflow."""

import os
from collections.abc import Mapping

PRESENTATION_DB = "/opt/airflow/project/nba_clutch.duckdb"


def pipeline_schedule(env: Mapping[str, str] | None = None) -> str | None:
    """The cron schedule for nba_clutch_pipeline, or None for manual runs only.

    It comes from NBA_PIPELINE_SCHEDULE in airflow/.env (Airflow reads cron times in UTC), and it's
    ignored while Airflow points at the presentation database, so switching back to it can never
    start a scheduled run there by accident.
    """
    env = os.environ if env is None else env
    schedule = (env.get("NBA_PIPELINE_SCHEDULE") or "").strip()
    if not schedule or env.get("NBA_DB_PATH", PRESENTATION_DB) == PRESENTATION_DB:
        return None
    return schedule
