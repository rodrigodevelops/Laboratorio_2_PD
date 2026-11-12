"""Registro de experimentos y modelos en MLflow.

El modelo vigente es la versión de ``modelo.nombre_registro`` que tiene el alias
``modelo.alias_vigente`` en el Model Registry. Promover un modelo es mover ese
alias; un reentrenamiento que no se promueve deja su corrida en el experimento,
pero no registra una versión ni toca el alias.

La dirección del servidor se toma de ``MLFLOW_TRACKING_URI``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from novamercado.modelo import Pronosticador
from novamercado.reentrenamiento import Resultado


class ModeloMLflow(mlflow.pyfunc.PythonModel):
    """Envoltura para guardar un ``Pronosticador`` como modelo de MLflow."""

    def load_context(self, context):
        self.pronosticador = Pronosticador.cargar(context.artifacts["modelo"])

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        return self.pronosticador.predecir(model_input)


def _nombre(params: dict) -> str:
    return params["modelo"]["nombre_registro"]


def _alias(params: dict) -> str:
    return params["modelo"]["alias_vigente"]


NO_EXISTE = {"RESOURCE_DOES_NOT_EXIST", "INVALID_PARAMETER_VALUE"}


def version_vigente(params: dict) -> str | None:
    """Versión con el alias vigente; ``None`` si no hay ninguna.

    Si MLflow no responde, la excepción se propaga: "no hay conexión" no es lo
    mismo que "no hay modelo", y confundirlos haría entrenar uno nuevo.
    """
    try:
        return str(MlflowClient().get_model_version_by_alias(_nombre(params), _alias(params)).version)
    except MlflowException as e:
        if e.error_code in NO_EXISTE:
            return None
        raise


def cargar_vigente(params: dict) -> tuple[Pronosticador, str]:
    """Descarga el modelo vigente. Lanza ``MlflowException`` si no hay o no hay conexión."""
    version = MlflowClient().get_model_version_by_alias(_nombre(params), _alias(params)).version
    modelo = mlflow.pyfunc.load_model(f"models:/{_nombre(params)}/{version}")
    return modelo.unwrap_python_model().pronosticador, str(version)


def _metricas_numericas(metricas: dict) -> dict:
    return {k: float(v) for k, v in metricas.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def registrar(resultado: Resultado, params: dict, etiquetas: dict | None = None, nombre_corrida: str = "reentrenamiento") -> str | None:
    """Guarda la corrida en el experimento. Si se promovió, registra la versión y mueve el alias.

    Devuelve la versión vigente al terminar.
    """
    mlflow.set_experiment(params["modelo"]["experimento"])
    anterior = version_vigente(params)
    with mlflow.start_run(run_name=nombre_corrida) as corrida:
        mlflow.log_params({f"lgbm.{k}": v for k, v in params["modelo"]["lgbm"].items()})
        mlflow.log_params({f"reentrenamiento.{k}": v for k, v in params["reentrenamiento"].items()})
        mlflow.log_metrics(_metricas_numericas(resultado.metricas))
        mlflow.set_tags({
            "promovido": str(resultado.promovido).lower(),
            "motivo": resultado.motivo,
            "vigente_anterior": anterior or "ninguno",
            **{k: str(v) for k, v in resultado.metricas.items() if isinstance(v, str)},
            **{k: str(v) for k, v in (etiquetas or {}).items()},
        })
        if resultado.comparacion is not None:
            with tempfile.TemporaryDirectory() as tmp:
                ruta = Path(tmp) / "comparacion.csv"
                resultado.comparacion.to_csv(ruta, index=False)
                mlflow.log_artifact(str(ruta))

        if not resultado.promovido or resultado.modelo is None:
            return anterior

        with tempfile.TemporaryDirectory() as tmp:
            resultado.modelo.guardar(Path(tmp) / "modelo")
            mlflow.set_tags({f"modelo.{k}": str(v) for k, v in resultado.modelo.info.items()})
            mlflow.log_dict(resultado.modelo.ajustes, "ajustes_cantidad_sugerida.json")
            info = mlflow.pyfunc.log_model(
                name="modelo",
                python_model=ModeloMLflow(),
                artifacts={"modelo": str(Path(tmp) / "modelo")},
                registered_model_name=_nombre(params),
            )
        version = str(info.registered_model_version)
        cliente = MlflowClient()
        cliente.set_model_version_tag(_nombre(params), version, "corrida", corrida.info.run_id)
        cliente.set_model_version_tag(_nombre(params), version, "motivo", resultado.motivo)
        cliente.set_registered_model_alias(_nombre(params), _alias(params), version)
        return version


def describir(params: dict) -> dict:
    return {"nombre": _nombre(params), "alias": _alias(params), "version": version_vigente(params)}


if __name__ == "__main__":  # pragma: no cover
    from novamercado.config import cargar_params

    print(json.dumps(describir(cargar_params()), indent=2))
