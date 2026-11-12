"""Registro en MLflow con un almacenamiento local (SQLite), sin servidor."""

import pandas as pd
import pytest

mlflow = pytest.importorskip("mlflow")

from novamercado.registro import cargar_vigente, registrar, version_vigente  # noqa: E402
from novamercado.reentrenamiento import Resultado, entrenamiento_inicial  # noqa: E402


@pytest.fixture
def mlflow_local(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.chdir(tmp_path)  # los artefactos se guardan en ./mlruns del directorio temporal
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield
    mlflow.set_tracking_uri(None)


def test_registro_y_alias(mlflow_local, historico, catalogo, feriados, params):
    assert version_vigente(params) is None
    inicial = entrenamiento_inicial(historico, catalogo, feriados, params)
    assert registrar(inicial, params) == "1"
    modelo, version = cargar_vigente(params)
    assert version == "1" and modelo.tipo == "lgbm"

    # Un reentrenamiento no promovido no registra versión ni mueve el alias.
    rechazado = Resultado(promovido=False, motivo="no alcanza", metricas={"costo_candidato": 1.0})
    assert registrar(rechazado, params) == "1"
    assert version_vigente(params) == "1"

    # Uno promovido crea la versión 2 y mueve el alias.
    assert registrar(inicial, params) == "2"
    assert cargar_vigente(params)[1] == "2"
