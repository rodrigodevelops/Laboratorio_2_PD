"""Entrena y registra el primer modelo si todavía no hay uno vigente.

Se ejecuta al levantar el producto. Si ya existe un modelo con el alias vigente,
no hace nada: al volver a levantarse, el producto no repite este trabajo.

Uso: ``python -m novamercado.inicializar``
"""

from __future__ import annotations

import sys
import time

from mlflow.exceptions import MlflowException

from novamercado.config import cargar_params, cargar_publicados
from novamercado.registro import registrar, version_vigente
from novamercado.reentrenamiento import entrenamiento_inicial


def inicializar(params: dict) -> str:
    existente = version_vigente(params)
    if existente:
        print(f"Ya hay un modelo vigente (versión {existente}); no se entrena de nuevo.")
        return existente
    catalogo, historico, feriados = cargar_publicados(params)
    print(f"Entrenando el primer modelo con {len(historico)} filas del histórico...")
    inicio = time.time()
    resultado = entrenamiento_inicial(historico, catalogo, feriados, params)
    version = registrar(resultado, params, {"origen": "inicial"}, nombre_corrida="modelo-inicial")
    print(f"{resultado.motivo}. Versión {version} registrada en {time.time() - inicio:.0f} s.")
    return version


def main() -> None:
    params = cargar_params()
    for intento in range(30):  # MLflow puede tardar en arrancar
        try:
            inicializar(params)
            return
        except MlflowException as e:
            print(f"MLflow no disponible ({e.__class__.__name__}); reintento {intento + 1}/30", file=sys.stderr)
            time.sleep(10)
    sys.exit(1)


if __name__ == "__main__":
    main()
