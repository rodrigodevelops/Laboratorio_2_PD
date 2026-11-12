"""Modelos de Pydantic del contrato del servicio (Anexo del enunciado).

Las solicitudes llegan como JSON libre, pasan por ``limpieza`` y el resultado se
valida aquí en modo estricto: si la limpieza tuviera un error, Pydantic lo
detecta antes de llegar al modelo. Las respuestas también se validan, para no
romper nunca el contrato.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator

Accion = Literal["reparar", "advertir"]
EstadoCalidad = Literal["ok", "corregido", "advertencia"]


class _Estricto(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


# ---------- Solicitudes ya limpias ----------

class FamiliaPromocion(_Estricto):
    familia_id: str
    en_promocion: NonNegativeInt


class SolicitudPrediccion(_Estricto):
    tienda_id: int
    fecha: date
    familias: list[FamiliaPromocion] = Field(min_length=1)


class VentaFamilia(_Estricto):
    familia_id: str
    ventas: float = Field(ge=0)


class SolicitudObservaciones(_Estricto):
    tienda_id: int
    fecha: date
    ventas: list[VentaFamilia]


# ---------- Calidad ----------

class ObservacionCalidad(BaseModel):
    campo: str
    accion: Accion
    detalle: str


class Calidad(BaseModel):
    estado: EstadoCalidad
    observaciones: list[ObservacionCalidad] = []

    @model_validator(mode="after")
    def _coherente(self):
        acciones = {o.accion for o in self.observaciones}
        esperado = "advertencia" if "advertir" in acciones else "corregido" if acciones else "ok"
        if self.estado != esperado:
            raise ValueError(f"estado '{self.estado}' no coincide con las observaciones")
        return self

    @classmethod
    def desde(cls, observaciones: list[ObservacionCalidad]) -> "Calidad":
        acciones = {o.accion for o in observaciones}
        estado = "advertencia" if "advertir" in acciones else "corregido" if acciones else "ok"
        return cls(estado=estado, observaciones=observaciones)


# ---------- Respuestas ----------

class PrediccionFamilia(BaseModel):
    familia_id: str
    venta_esperada: float
    cantidad_sugerida: NonNegativeInt


class RespuestaPrediccion(BaseModel):
    tienda_id: int
    fecha: date
    version_modelo: str
    predicciones: list[PrediccionFamilia]
    calidad: Calidad


class RespuestaObservaciones(BaseModel):
    registros_guardados: NonNegativeInt
    calidad: Calidad


class RespuestaReentrenarInicio(BaseModel):
    id: str


class EstadoReentrenamiento(BaseModel):
    estado: Literal["en_curso", "exitoso", "fallido"]
    promovido: bool | None = None
    version: str | None = None
    motivo: str | None = None


class ModeloVigente(BaseModel):
    nombre: str
    alias: str
    version: str
