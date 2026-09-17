from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="nba_clutch_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command="cd /opt/airflow/project/dbt && dbt run --profiles-dir /opt/airflow/project/dbt",
    )
    run_extract = BashOperator(
        task_id="run_extract",
        bash_command="cd /opt/airflow/project && python3 pipeline/main.py",
    )
    run_load_shots = BashOperator(
        task_id="run_load_shots",
        bash_command="cd /opt/airflow/project && python3 pipeline/load_shots.py",
    )
    run_extract >> run_dbt >> run_load_shots
