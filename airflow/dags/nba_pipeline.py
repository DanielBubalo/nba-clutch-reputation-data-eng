from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

with DAG(
    dag_id="nba_clutch_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:
    run_extract = BashOperator(
        task_id="run_extract",
        bash_command="cd /opt/airflow/project && python3 -u pipeline/main.py",
    )
    run_dbt_deps = BashOperator(
        task_id="run_dbt_deps",
        bash_command="cd /opt/airflow/project/dbt && dbt deps --profiles-dir /opt/airflow/project/dbt",
    )
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command="cd /opt/airflow/project/dbt && dbt build --profiles-dir /opt/airflow/project/dbt",
    )
    trigger_shots = TriggerDagRunOperator(
        task_id="trigger_shots",
        trigger_dag_id="nba_clutch_shots",
    )

    run_extract >> run_dbt_deps >> run_dbt >> trigger_shots
