from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

from agent_callbacks import diagnose_failure

DBT = "/home/airflow/dbt_venv/bin/dbt"

with DAG(
    dag_id="nba_clutch_shots",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    # Any failed task gets a diagnosis report from the pipeline agent (see agent_callbacks.py).
    default_args={"on_failure_callback": diagnose_failure},
) as dag:
    run_load_shots = BashOperator(
        task_id="run_load_shots",
        bash_command="cd /opt/airflow/project && python3 -u pipeline/load_shots.py",
    )
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command=f"cd /opt/airflow/project/dbt && {DBT} build --profiles-dir /opt/airflow/project/dbt",
    )

    run_load_shots >> run_dbt
