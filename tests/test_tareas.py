"""Reentrenamiento de punta a punta (los mismos pasos que ejecuta el DAG).

Usa SQLite como base del producto y como almacenamiento de MLflow: no necesita
Airflow, PostgreSQL ni un servidor de MLflow.
"""

import copy
import shutil

import pandas as pd
import pytest

mlflow = pytest.importorskip("mlflow")

from novamercado import db, registro, tareas  # noqa: E402
from novamercado.reentrenamiento import entrenamiento_inicial  # noqa: E402

INICIO_OPERACION = pd.Timestamp("2025-11-17")


@pytest.fixture
def entorno(tmp_path, monkeypatch, dir_catalogos, historico, catalogo, feriados, params):
    # Archivos publicados: el histórico termina antes de la operación simulada.
    publicados = tmp_path / "publicados"
    shutil.copytree(dir_catalogos, publicados)
    historico[historico["fecha"] < INICIO_OPERACION].to_csv(publicados / "historico_ventas.csv", index=False)

    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("NOVAMERCADO_DATOS", str(publicados))
    monkeypatch.setenv("NOVAMERCADO_TRABAJO", str(tmp_path / "trabajo"))
    mlflow.set_tracking_uri(uri)

    p = copy.deepcopy(params)
    p["datos"] = {"dir_publicados": str(publicados)}
    motor = db.crear_motor(f"sqlite:///{tmp_path / 'producto.db'}")
    db.crear_tablas(motor)

    # Modelo vigente inicial (versión 1), como lo deja el inicializador.
    inicial = entrenamiento_inicial(historico[historico["fecha"] < INICIO_OPERACION], catalogo, feriados, p)
    registro.registrar(inicial, p)
    yield {"motor": motor, "params": p}
    mlflow.set_tracking_uri(None)


def _operar(motor, historico, factor_sugerida: float) -> None:
    """Registra dos semanas de operación: predicciones de la versión 1 y ventas reales."""
    reales = historico[historico["fecha"] >= INICIO_OPERACION]
    with motor.begin() as con:
        for (fecha, tienda), dia in reales.groupby(["fecha", "tienda_id"]):
            id_ = db.registrar_solicitud(con, "prediccion", {}, "ok", tienda, fecha.date(), version="1")
            db.registrar_predicciones(con, id_, tienda, fecha.date(), [
                {"familia_id": r.familia_id, "en_promocion": int(r.en_promocion), "venta_esperada": float(r.ventas),
                 "cantidad_sugerida": int(r.ventas * factor_sugerida)}
                for r in dia.itertuples()
            ], "1")
            id_ = db.registrar_solicitud(con, "observaciones", {}, "ok", tienda, fecha.date())
            db.guardar_observaciones(con, id_, tienda, fecha.date(), [
                {"familia_id": r.familia_id, "ventas": float(r.ventas), "atipica": False} for r in dia.itertuples()
            ])


def _ejecutar(run_id, entorno):
    tareas.extraer(run_id, entorno["params"], entorno["motor"])
    tareas.entrenar(run_id, entorno["params"])
    return tareas.registrar(run_id, entorno["params"], entorno["motor"])


def test_reentrenamiento_promueve_si_el_vigente_fue_peor(entorno, historico):
    _operar(entorno["motor"], historico, factor_sugerida=3.0)  # el vigente sugirió el triple
    db.crear_reentrenamiento(entorno["motor"], "reentrenar_a")
    salida = _ejecutar("reentrenar_a", entorno)

    assert salida["promovido"] is True and salida["version"] == "2"
    assert registro.version_vigente(entorno["params"]) == "2"
    fila = db.obtener_reentrenamiento(entorno["motor"], "reentrenar_a")
    assert fila["estado"] == "exitoso" and fila["promovido"] and fila["version"] == "2"
    assert "Costo en validación" in fila["motivo"]


def test_reentrenamiento_no_toca_al_vigente_si_no_mejora(entorno, historico):
    _operar(entorno["motor"], historico, factor_sugerida=1.0)  # el vigente acertó exacto
    salida = _ejecutar("manual__desde_la_interfaz", entorno)  # sin registro previo en la API

    assert salida["promovido"] is False and salida["version"] == "1"
    assert registro.version_vigente(entorno["params"]) == "1"
    fila = db.obtener_reentrenamiento(entorno["motor"], "manual__desde_la_interfaz")
    assert fila["estado"] == "exitoso" and fila["promovido"] is False


def test_sin_operacion_no_hay_evidencia(entorno):
    salida = _ejecutar("reentrenar_b", entorno)
    assert salida["promovido"] is False and "evidencia" in salida["motivo"]
    assert registro.version_vigente(entorno["params"]) == "1"


def test_el_dag_se_puede_cargar():
    """Solo si Airflow está instalado (no lo está en el CI)."""
    pytest.importorskip("airflow")
    from airflow.models.dagbag import DagBag

    dagbag = DagBag(dag_folder="dags", include_examples=False)
    assert not dagbag.import_errors
    assert list(dagbag.dags["reentrenamiento"].task_dict) == ["extraer", "entrenar", "registrar"]
