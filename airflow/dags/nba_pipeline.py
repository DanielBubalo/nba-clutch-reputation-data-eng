from datetime import datetime

from airflow.sdk import DAG  # type: ignore
from airflow.providers.standard.operators.bash import BashOperator  # type: ignore
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator  # type: ignore

from agent_callbacks import diagnose_failure
from pipeline_schedule import pipeline_schedule

DBT = "/home/airflow/dbt_venv/bin/dbt"

with DAG(
    dag_id="nba_clutch_pipeline",
    start_date=datetime(2024, 1, 1),
    # Manual unless airflow/.env sets NBA_PIPELINE_SCHEDULE, and never on the presentation database
    # (see pipeline_schedule.py). catchup=False: after a missed day, it runs once, not once per day.
    schedule=pipeline_schedule(),
    catchup=False,
    # One run at a time: DuckDB allows a single writer, so a slow run must never overlap the next.
    max_active_runs=1,
    # Any failed task gets a diagnosis report from the pipeline agent (see agent_callbacks.py).
    default_args={"on_failure_callback": diagnose_failure},
) as dag:
    run_extract = BashOperator(
        task_id="run_extract",
        bash_command="cd /opt/airflow/project && python3 -u pipeline/main.py",
    )
    run_dbt_deps = BashOperator(
        task_id="run_dbt_deps",
        bash_command=f"cd /opt/airflow/project/dbt && {DBT} deps --profiles-dir /opt/airflow/project/dbt",
    )
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command=f"cd /opt/airflow/project/dbt && {DBT} build --exclude tag:shots --profiles-dir /opt/airflow/project/dbt",
    )
    trigger_shots = TriggerDagRunOperator(
        task_id="trigger_shots",
        trigger_dag_id="nba_clutch_shots",
    )

    run_extract >> run_dbt_deps >> run_dbt >> trigger_shots
