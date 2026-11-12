"""Configuración versionada (config/params.yaml) y archivos publicados."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yaml

from novamercado.catalogos import Catalogo, cargar_catalogo
from novamercado.features import leer_feriados

RAIZ = Path(__file__).resolve().parents[2]


def cargar_params(ruta: str | Path | None = None) -> dict:
    ruta = Path(ruta or os.environ.get("NOVAMERCADO_PARAMS", RAIZ / "config" / "params.yaml"))
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dir_publicados(params: dict) -> Path:
    """Carpeta de archivos publicados. ``NOVAMERCADO_DATOS`` tiene prioridad."""
    ruta = Path(os.environ.get("NOVAMERCADO_DATOS", params["datos"]["dir_publicados"]))
    return ruta if ruta.is_absolute() else RAIZ / ruta


def cargar_publicados(params: dict) -> tuple[Catalogo, pd.DataFrame, pd.DataFrame]:
    """Catálogo, histórico de ventas y feriados."""
    d = dir_publicados(params)
    historico = pd.read_csv(d / "historico_ventas.csv", parse_dates=["fecha"])
    return cargar_catalogo(d), historico, leer_feriados(d / "feriados.csv")
