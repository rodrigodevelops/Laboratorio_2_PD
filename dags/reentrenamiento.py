"""Reentrenamiento del modelo de pronóstico.

Lo dispara ``POST /admin/reentrenar`` (o la interfaz de Airflow). El DAG solo
orquesta: cada tarea ejecuta un paso de ``novamercado.tareas`` con el entorno
virtual del producto (``/opt/airflow/novamercado-venv``), separado del Python de
Airflow para que sus dependencias no choquen.

1. ``extraer``: datos de la base del producto y versión vigente en MLflow.
2. ``entrenar``: candidato y criterio de reemplazo.
3. ``registrar``: corrida en MLflow, versión y alias si se promueve, y resultado
   en la base del producto para ``GET /admin/reentrenar/{id}``.

Si una tarea falla, el alias no se mueve y el modelo vigente sigue igual; la API
detecta el fallo al consultar el estado de la ejecución.

Las credenciales se leen de variables de entorno del contenedor dentro del
comando: no aparecen en las plantillas renderizadas de la interfaz.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

PYTHON = "/opt/airflow/novamercado-venv/bin/python"
ENTORNO = (
    'DATABASE_URL="$NOVAMERCADO_DATABASE_URL" '
    'MLFLOW_TRACKING_URI="$NOVAMERCADO_MLFLOW_URI" '
    "PYTHONPATH=/opt/airflow/novamercado/src "
)


def paso(nombre: str) -> str:
    return ENTORNO + f'{PYTHON} -m novamercado.tareas {nombre} --run-id "{{{{ run_id }}}}"'


@dag(
    dag_id="reentrenamiento",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # dos reentrenamientos a la vez podrían pisarse el alias
    dagrun_timeout=timedelta(minutes=15),
    default_args={"retries": 0, "execution_timeout": timedelta(minutes=10)},
    tags=["novamercado"],
    doc_md=__doc__,
)
def reentrenamiento():
    extraer = BashOperator(task_id="extraer", bash_command=paso("extraer"))
    entrenar = BashOperator(task_id="entrenar", bash_command=paso("entrenar"))
    registrar = BashOperator(task_id="registrar", bash_command=paso("registrar"))
    extraer >> entrenar >> registrar


reentrenamiento()
