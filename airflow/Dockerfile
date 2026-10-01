FROM apache/airflow:3.3.1

# Pipeline packages, installed alongside airflow and held to its tested versions
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.13.txt"

# dbt's own virtual environment, since the dependencies conflicts with airflow's
COPY requirements-dbt.txt /requirements-dbt.txt
RUN python -m venv /home/airflow/dbt_venv \
    && /home/airflow/dbt_venv/bin/pip install --no-cache-dir -r /requirements-dbt.txt