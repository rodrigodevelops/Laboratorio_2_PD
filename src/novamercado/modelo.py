"""Modelos de pronóstico y cantidad sugerida.

- ``baseline``: promedio de las ventas del mismo día de la semana en las últimas
  4 semanas (si no hay, media de 28 días; si no, la última venta).
- ``lgbm``: un LightGBM global para todas las tiendas y familias.

Cantidad sugerida (los dos modelos usan el mismo método, para comparar justo):
para cada familia, el óptimo es el cuantil ``τ = faltante / (faltante + sobrante)``
de la demanda. En un periodo que el modelo no vio (calibración) se mide el error
``log1p(real) − log1p(esperada)`` y se guarda su cuantil τ por familia. La
sugerida es ``expm1(log1p(esperada) + ajuste)``, redondeada a entero ≥ 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from novamercado.features import CATEGORICAS, VARIABLES, matriz

TIPOS = ("baseline", "lgbm")


def ratio_critico(costos: dict[str, tuple[float, float]]) -> dict[str, float]:
    return {f: cf / (cf + cs) for f, (cf, cs) in costos.items()}


class Pronosticador:
    def __init__(self, tipo: str, costos: dict[str, tuple[float, float]]):
        if tipo not in TIPOS:
            raise ValueError(f"tipo de modelo desconocido: {tipo}")
        self.tipo = tipo
        self.costos = {f: tuple(v) for f, v in costos.items()}
        self.tau = ratio_critico(self.costos)
        self.booster: lgb.Booster | None = None
        self.ajustes: dict[str, float] = {f: 0.0 for f in self.costos}
        self.info: dict = {}

    # -------------------------------------------------------------- entrenamiento

    def entrenar(self, tabla: pd.DataFrame, params: dict) -> "Pronosticador":
        if self.tipo == "lgbm":
            p = {k: v for k, v in params.items() if k != "num_boost_round"}
            p.update(verbose=-1, deterministic=True, force_row_wise=True)
            datos = lgb.Dataset(matriz(tabla), label=tabla["ventas"], categorical_feature=CATEGORICAS)
            self.booster = lgb.train(p, datos, num_boost_round=params.get("num_boost_round", 600))
        self.info["filas_entrenamiento"] = int(len(tabla))
        if len(tabla):
            self.info["entrenado_hasta"] = str(pd.Timestamp(tabla["fecha"].max()).date())
        return self

    def calibrar(self, tabla: pd.DataFrame) -> "Pronosticador":
        """Cuantil τ del error en escala logarítmica, por familia."""
        if len(tabla) == 0:
            return self
        error = np.log1p(tabla["ventas"].clip(lower=0).to_numpy()) - np.log1p(self.esperada(tabla))
        por_familia = pd.Series(error).groupby(tabla["familia_id"].to_numpy())
        for familia, valores in por_familia:
            if familia in self.tau and len(valores) >= 10:
                self.ajustes[familia] = float(np.quantile(valores, self.tau[familia]))
        self.info["filas_calibracion"] = int(len(tabla))
        return self

    # -------------------------------------------------------------- predicción

    def esperada(self, tabla: pd.DataFrame) -> np.ndarray:
        if self.tipo == "lgbm":
            if self.booster is None:
                raise RuntimeError("el modelo no está entrenado")
            valor = self.booster.predict(matriz(tabla))
        else:
            valor = (
                tabla["media_dia_semana"]
                .fillna(tabla["media28"])
                .fillna(tabla["lag1"])
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
        return np.clip(np.nan_to_num(valor, nan=0.0), 0, None)

    def predecir(self, tabla: pd.DataFrame) -> pd.DataFrame:
        esperada = self.esperada(tabla)
        ajuste = tabla["familia_id"].map(self.ajustes).fillna(0.0).to_numpy(dtype=float)
        sugerida = np.rint(np.expm1(np.log1p(esperada) + ajuste)).clip(min=0).astype(int)
        return pd.DataFrame(
            {
                "familia_id": tabla["familia_id"].to_numpy(),
                "venta_esperada": np.round(esperada, 1),
                "cantidad_sugerida": sugerida,
            }
        )

    # -------------------------------------------------------------- persistencia

    def guardar(self, directorio: str | Path) -> Path:
        d = Path(directorio)
        d.mkdir(parents=True, exist_ok=True)
        if self.booster is not None:
            self.booster.save_model(str(d / "booster.txt"))
        meta = {"tipo": self.tipo, "costos": self.costos, "ajustes": self.ajustes,
                "info": self.info, "variables": VARIABLES}
        (d / "modelo.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        return d

    @classmethod
    def cargar(cls, directorio: str | Path) -> "Pronosticador":
        d = Path(directorio)
        meta = json.loads((d / "modelo.json").read_text())
        modelo = cls(meta["tipo"], {f: tuple(v) for f, v in meta["costos"].items()})
        modelo.ajustes = meta["ajustes"]
        modelo.info = meta.get("info", {})
        if (d / "booster.txt").exists():
            modelo.booster = lgb.Booster(model_file=str(d / "booster.txt"))
        return modelo
