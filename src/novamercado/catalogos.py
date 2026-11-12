"""Catálogos de tiendas y familias, leídos de los archivos publicados."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Tienda:
    tienda_id: int
    nombre: str
    ciudad: str
    tipo: str
    fecha_apertura: date


@dataclass(frozen=True)
class Catalogo:
    tiendas: dict[int, Tienda]
    familias: dict[str, str]  # familia_id -> nombre legible
    costos: dict[str, tuple[float, float]] = field(default_factory=dict)  # (faltante, sobrante)

    @property
    def ids_familias(self) -> list[str]:
        return sorted(self.familias)


def _leer(ruta: Path) -> list[dict[str, str]]:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def cargar_catalogo(directorio: str | Path) -> Catalogo:
    d = Path(directorio)
    tiendas = {
        int(r["tienda_id"]): Tienda(
            tienda_id=int(r["tienda_id"]),
            nombre=r["nombre"],
            ciudad=r["ciudad"],
            tipo=r["tipo"],
            fecha_apertura=date.fromisoformat(r["fecha_apertura"]),
        )
        for r in _leer(d / "tiendas.csv")
    }
    familias = {r["familia_id"]: r["nombre"] for r in _leer(d / "familias.csv")}
    costos = {}
    if (d / "costos.csv").exists():
        costos = {
            r["familia_id"]: (float(r["costo_faltante"]), float(r["costo_sobrante"]))
            for r in _leer(d / "costos.csv")
        }
    return Catalogo(tiendas=tiendas, familias=familias, costos=costos)
