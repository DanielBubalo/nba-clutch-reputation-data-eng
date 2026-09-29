from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    dag_id="nba_clutch_shots",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:
    run_load_shots = BashOperator(
        task_id="run_load_shots",
        bash_command="cd /opt/airflow/project && python3 -u pipeline/load_shots.py",
    )
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command="cd /opt/airflow/project/dbt && dbt build --profiles-dir /opt/airflow/project/dbt",
    )

    run_load_shots >> run_dbt
