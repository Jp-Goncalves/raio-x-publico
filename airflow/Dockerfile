FROM apache/airflow:3.4.0-python3.12

# Venv separado com as dependências do projeto (requirements.txt): evita que os
# pins do dbt-core briguem com os do próprio Airflow. As tarefas do DAG chamam
# o Python e o dbt por esse venv.
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /home/airflow/project-venv \
    && /home/airflow/project-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
