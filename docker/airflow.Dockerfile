# Airflow 3 con un entorno virtual aparte para el código del producto.
#
# Las tareas del DAG ejecutan el código con /opt/airflow/novamercado-venv, no con
# el Python de Airflow: así las versiones de pandas, SQLAlchemy o MLflow del
# producto no chocan con las que Airflow necesita.
FROM apache/airflow:3.2.2

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements-servicio.txt /tmp/requirements-servicio.txt
RUN python -m venv /opt/airflow/novamercado-venv \
    && /opt/airflow/novamercado-venv/bin/pip install --no-cache-dir -r /tmp/requirements-servicio.txt

COPY --chown=airflow:root src /opt/airflow/novamercado/src
COPY --chown=airflow:root config /opt/airflow/novamercado/config
