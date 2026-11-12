"""Métricas técnicas y de negocio."""

from __future__ import annotations

import numpy as np


def costo(real, sugerida, familias, costos: dict[str, tuple[float, float]]) -> float:
    """costo = faltante · máx(real − sugerida, 0) + sobrante · máx(sugerida − real, 0)."""
    real = np.asarray(real, dtype=float)
    sugerida = np.asarray(sugerida, dtype=float)
    cf = np.array([costos[f][0] for f in familias], dtype=float)
    cs = np.array([costos[f][1] for f in familias], dtype=float)
    return float(np.sum(cf * np.maximum(real - sugerida, 0) + cs * np.maximum(sugerida - real, 0)))


def wape(real, esperada) -> float:
    real = np.asarray(real, dtype=float)
    total = real.sum()
    return float(np.abs(real - np.asarray(esperada, dtype=float)).sum() / total) if total > 0 else float("nan")


def mae(real, esperada) -> float:
    return float(np.mean(np.abs(np.asarray(real, dtype=float) - np.asarray(esperada, dtype=float))))


def formato_miles(valor: float) -> str:
    """18210.4 -> '18 210'."""
    return f"{valor:,.0f}".replace(",", " ")
