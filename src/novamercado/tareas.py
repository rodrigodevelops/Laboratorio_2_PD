"""Pasos del reentrenamiento. El DAG de Airflow solo los ejecuta en orden.

    python -m novamercado.tareas extraer   --run-id <id>
    python -m novamercado.tareas entrenar  --run-id <id>
    python -m novamercado.tareas registrar --run-id <id>

Cada paso lee lo que dejó el anterior en una carpeta de trabajo propia de la
ejecución, así que se puede repetir un paso sin repetir los anteriores.

- ``extraer``: histórico publicado, observaciones, promociones solicitadas y
  predicciones del modelo vigente (desde la base de datos del producto).
- ``entrenar``: aplica el criterio de reemplazo (``reentrenamiento.reentrenar``).
- ``registrar``: guarda la corrida en MLflow; si se promovió, registra la versión
  y mueve el alias. Al final escribe el resultado en la tabla
  ``reentrenamientos``, que es lo que consulta ``GET /admin/reentrenar/{id}``.

Si un paso falla, el alias no se mueve: el modelo vigente no cambia.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import pandas as pd

from novamercado import db, registro
from novamercado.config import cargar_params, cargar_publicados
from novamercado.modelo import Pronosticador
from novamercado.reentrenamiento import Resultado, entrenamiento_inicial, reentrenar

ARCHIVOS = ("observaciones", "promociones", "predicciones_vigente")


def carpeta_trabajo(run_id: str) -> Path:
    base = Path(os.environ.get("NOVAMERCADO_TRABAJO", "/tmp/novamercado-reentrenamiento"))
    carpeta = base / re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _leer(ruta: Path) -> pd.DataFrame:
    df = pd.read_csv(ruta)
    if "fecha" in df:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def extraer(run_id: str, params: dict, motor=None) -> dict:
    carpeta = carpeta_trabajo(run_id)
    motor = motor or db.crear_motor()
    vigente = registro.version_vigente(params)
    datos = db.datos_reentrenamiento(motor, vigente)
    for nombre in ARCHIVOS:
        datos[nombre].to_csv(carpeta / f"{nombre}.csv", index=False)
    resumen = {"vigente": vigente, **{f"filas_{k}": int(len(v)) for k, v in datos.items()}}
    if len(datos["observaciones"]):
        fechas = pd.to_datetime(datos["observaciones"]["fecha"])
        resumen["observaciones_desde"] = str(fechas.min().date())
        resumen["observaciones_hasta"] = str(fechas.max().date())
    (carpeta / "extraccion.json").write_text(json.dumps(resumen, indent=2))
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    return resumen


def entrenar(run_id: str, params: dict) -> Resultado:
    carpeta = carpeta_trabajo(run_id)
    extraccion = json.loads((carpeta / "extraccion.json").read_text())
    catalogo, historico, feriados = cargar_publicados(params)
    if extraccion["vigente"] is None:
        # No hay modelo vigente (registro vacío): se entrena como al arrancar.
        resultado = entrenamiento_inicial(historico, catalogo, feriados, params)
    else:
        d = {n: _leer(carpeta / f"{n}.csv") for n in ARCHIVOS}
        resultado = reentrenar(historico, d["observaciones"], d["promociones"], d["predicciones_vigente"],
                               catalogo, feriados, params)

    decision = {"promovido": resultado.promovido, "motivo": resultado.motivo, "metricas": resultado.metricas}
    (carpeta / "decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False, default=str))
    if resultado.comparacion is not None:
        resultado.comparacion.to_csv(carpeta / "comparacion.csv", index=False)
    if resultado.modelo is not None:
        resultado.modelo.guardar(carpeta / "modelo")
    print(json.dumps(decision, indent=2, ensure_ascii=False, default=str))
    return resultado


def registrar(run_id: str, params: dict, motor=None) -> dict:
    carpeta = carpeta_trabajo(run_id)
    decision = json.loads((carpeta / "decision.json").read_text())
    extraccion = json.loads((carpeta / "extraccion.json").read_text())
    resultado = Resultado(
        promovido=decision["promovido"],
        motivo=decision["motivo"],
        metricas=decision["metricas"],
        modelo=Pronosticador.cargar(carpeta / "modelo") if (carpeta / "modelo").exists() else None,
        comparacion=_leer(carpeta / "comparacion.csv") if (carpeta / "comparacion.csv").exists() else None,
    )
    etiquetas = {"origen": "reentrenamiento", "dag_run_id": run_id,
                 **{k: v for k, v in extraccion.items() if v is not None}}
    version = registro.registrar(resultado, params, etiquetas, nombre_corrida=f"reentrenamiento-{run_id}")

    motor = motor or db.crear_motor()
    if db.obtener_reentrenamiento(motor, run_id) is None:  # disparado desde la interfaz de Airflow
        db.crear_reentrenamiento(motor, run_id)
    db.actualizar_reentrenamiento(motor, run_id, estado="exitoso", promovido=resultado.promovido,
                                  version=version, motivo=resultado.motivo)
    salida = {"estado": "exitoso", "promovido": resultado.promovido, "version": version, "motivo": resultado.motivo}
    print(json.dumps(salida, indent=2, ensure_ascii=False))
    return salida


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="novamercado.tareas")
    parser.add_argument("paso", choices=["extraer", "entrenar", "registrar"])
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    params = cargar_params()
    {"extraer": extraer, "entrenar": entrenar, "registrar": registrar}[args.paso](args.run_id, params)


if __name__ == "__main__":
    main()
