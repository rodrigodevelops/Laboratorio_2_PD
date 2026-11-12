"""Base de datos propia del producto (PostgreSQL en Docker; SQLite en las pruebas).

Tablas:

- ``solicitudes``: cada llamada a la API, con su cuerpo original, el estado de
  calidad o el motivo del rechazo y la versión del modelo.
- ``correcciones``: cada observación de calidad (reparar o advertir).
- ``predicciones``: lo que el servicio respondió, por familia, con su versión.
- ``observaciones``: la venta real vigente por fecha, tienda y familia. La llave
  primaria impide duplicados; reenviar el mismo valor no escribe nada.
- ``observaciones_historial``: cada cambio de una observación, para auditar.
- ``reentrenamientos``: ejecuciones del DAG y su resultado.

Se usa SQLAlchemy Core con SQL portable, para que las pruebas corran sin
PostgreSQL. Todo lo que escribe una solicitud ocurre en una transacción.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection, Engine

meta = MetaData()

solicitudes = Table(
    "solicitudes", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("recibida_en", DateTime(timezone=True), nullable=False),
    Column("endpoint", String(40), nullable=False),
    Column("tienda_id", Integer),
    Column("fecha", Date),
    Column("cuerpo", JSON),
    Column("estado", String(20), nullable=False),  # ok, corregido, advertencia, rechazada, error
    Column("detalle", Text),
    Column("version_modelo", String(20)),
)

correcciones = Table(
    "correcciones", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("solicitud_id", Integer, ForeignKey("solicitudes.id"), nullable=False, index=True),
    Column("campo", String(200), nullable=False),
    Column("accion", String(20), nullable=False),
    Column("detalle", Text, nullable=False),
)

predicciones = Table(
    "predicciones", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("solicitud_id", Integer, ForeignKey("solicitudes.id"), nullable=False, index=True),
    Column("tienda_id", Integer, nullable=False),
    Column("fecha", Date, nullable=False),
    Column("familia_id", String(40), nullable=False),
    Column("en_promocion", Integer, nullable=False),
    Column("venta_esperada", Float, nullable=False),
    Column("cantidad_sugerida", Integer, nullable=False),
    Column("version_modelo", String(20), nullable=False, index=True),
)

observaciones = Table(
    "observaciones", meta,
    Column("tienda_id", Integer, primary_key=True),
    Column("fecha", Date, primary_key=True),
    Column("familia_id", String(40), primary_key=True),
    Column("ventas", Float, nullable=False),
    Column("atipica", Boolean, nullable=False, default=False),
    Column("solicitud_id", Integer, ForeignKey("solicitudes.id")),
    Column("actualizada_en", DateTime(timezone=True), nullable=False),
)

observaciones_historial = Table(
    "observaciones_historial", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tienda_id", Integer, nullable=False),
    Column("fecha", Date, nullable=False),
    Column("familia_id", String(40), nullable=False),
    Column("ventas_anterior", Float),
    Column("ventas_nueva", Float, nullable=False),
    Column("solicitud_id", Integer, ForeignKey("solicitudes.id")),
    Column("registrada_en", DateTime(timezone=True), nullable=False),
)

reentrenamientos = Table(
    "reentrenamientos", meta,
    Column("id", String(80), primary_key=True),
    Column("creado_en", DateTime(timezone=True), nullable=False),
    Column("actualizado_en", DateTime(timezone=True), nullable=False),
    Column("estado", String(20), nullable=False),  # en_curso, exitoso, fallido
    Column("promovido", Boolean),
    Column("version", String(20)),
    Column("motivo", Text),
)


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def crear_motor(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL", "sqlite:///novamercado.db")
    opciones = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        opciones["connect_args"] = {"connect_timeout": 3}
    return create_engine(url, **opciones)


def crear_tablas(motor: Engine) -> None:
    meta.create_all(motor)


def disponible(motor: Engine) -> bool:
    try:
        with motor.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- escritura

def registrar_solicitud(
    con: Connection, endpoint: str, cuerpo, estado: str, tienda_id=None, fecha=None,
    detalle: str | None = None, version: str | None = None, calidad=None,
) -> int:
    try:
        json.dumps(cuerpo)
    except (TypeError, ValueError):
        cuerpo = {"no_serializable": repr(cuerpo)[:2000]}
    id_ = con.execute(insert(solicitudes).values(
        recibida_en=ahora(), endpoint=endpoint, tienda_id=tienda_id, fecha=fecha,
        cuerpo=cuerpo, estado=estado, detalle=detalle, version_modelo=version,
    )).inserted_primary_key[0]
    if calidad:
        con.execute(insert(correcciones), [
            {"solicitud_id": id_, "campo": o.campo, "accion": o.accion, "detalle": o.detalle} for o in calidad
        ])
    return int(id_)


def registrar_predicciones(con: Connection, solicitud_id: int, tienda_id: int, fecha: date,
                           filas: list[dict], version: str) -> None:
    con.execute(insert(predicciones), [
        {"solicitud_id": solicitud_id, "tienda_id": tienda_id, "fecha": fecha, "version_modelo": version, **f}
        for f in filas
    ])


def guardar_observaciones(con: Connection, solicitud_id: int, tienda_id: int, fecha: date,
                          ventas: list[dict]) -> int:
    """Inserta o actualiza. Devuelve cuántos registros son nuevos o cambiaron."""
    existentes = {
        r.familia_id: r.ventas
        for r in con.execute(select(observaciones.c.familia_id, observaciones.c.ventas).where(and_(
            observaciones.c.tienda_id == tienda_id, observaciones.c.fecha == fecha)))
    }
    cambios = 0
    for v in ventas:
        anterior = existentes.get(v["familia_id"])
        if anterior is not None and anterior == v["ventas"]:
            continue
        valores = {"ventas": v["ventas"], "atipica": v["atipica"], "solicitud_id": solicitud_id, "actualizada_en": ahora()}
        if anterior is None:
            con.execute(insert(observaciones).values(tienda_id=tienda_id, fecha=fecha, familia_id=v["familia_id"], **valores))
        else:
            con.execute(update(observaciones).where(and_(
                observaciones.c.tienda_id == tienda_id, observaciones.c.fecha == fecha,
                observaciones.c.familia_id == v["familia_id"])).values(**valores))
        con.execute(insert(observaciones_historial).values(
            tienda_id=tienda_id, fecha=fecha, familia_id=v["familia_id"], ventas_anterior=anterior,
            ventas_nueva=v["ventas"], solicitud_id=solicitud_id, registrada_en=ahora()))
        cambios += 1
    return cambios


# ---------------------------------------------------------------- lectura

def observaciones_tienda(motor: Engine, tienda_id: int, desde: date, hasta: date) -> pd.DataFrame:
    """Ventas reales utilizables (no atípicas) de una tienda entre dos fechas."""
    consulta = select(observaciones.c.fecha, observaciones.c.tienda_id, observaciones.c.familia_id,
                      observaciones.c.ventas).where(and_(
        observaciones.c.tienda_id == tienda_id, observaciones.c.fecha >= desde,
        observaciones.c.fecha <= hasta, observaciones.c.atipica.is_(False)))
    with motor.connect() as c:
        return pd.DataFrame(c.execute(consulta).all(), columns=["fecha", "tienda_id", "familia_id", "ventas"])


def datos_reentrenamiento(motor: Engine, version_vigente: str | None) -> dict[str, pd.DataFrame]:
    """Observaciones utilizables, promociones solicitadas y predicciones del vigente.

    Para promociones y predicciones se toma la última solicitud de cada fecha,
    tienda y familia.
    """
    with motor.connect() as c:
        obs = pd.DataFrame(c.execute(select(
            observaciones.c.fecha, observaciones.c.tienda_id, observaciones.c.familia_id, observaciones.c.ventas,
        ).where(observaciones.c.atipica.is_(False))).all(), columns=["fecha", "tienda_id", "familia_id", "ventas"])

        ultima = (select(func.max(predicciones.c.id).label("id"))
                  .group_by(predicciones.c.tienda_id, predicciones.c.fecha, predicciones.c.familia_id))
        promos = pd.DataFrame(c.execute(select(
            predicciones.c.fecha, predicciones.c.tienda_id, predicciones.c.familia_id, predicciones.c.en_promocion,
        ).where(predicciones.c.id.in_(ultima))).all(), columns=["fecha", "tienda_id", "familia_id", "en_promocion"])

        columnas = ["fecha", "tienda_id", "familia_id", "cantidad_sugerida", "venta_esperada"]
        pred = pd.DataFrame(columns=columnas)
        if version_vigente is not None:
            ultima_vigente = ultima.where(predicciones.c.version_modelo == version_vigente)
            pred = pd.DataFrame(c.execute(select(
                predicciones.c.fecha, predicciones.c.tienda_id, predicciones.c.familia_id,
                predicciones.c.cantidad_sugerida, predicciones.c.venta_esperada,
            ).where(predicciones.c.id.in_(ultima_vigente))).all(), columns=columnas)
    return {"observaciones": obs, "promociones": promos, "predicciones_vigente": pred}


# ---------------------------------------------------------------- reentrenamientos

def crear_reentrenamiento(motor: Engine, id_: str) -> None:
    with motor.begin() as c:
        c.execute(insert(reentrenamientos).values(
            id=id_, creado_en=ahora(), actualizado_en=ahora(), estado="en_curso"))


def actualizar_reentrenamiento(motor: Engine, id_: str, **valores) -> None:
    with motor.begin() as c:
        c.execute(update(reentrenamientos).where(reentrenamientos.c.id == id_)
                  .values(actualizado_en=ahora(), **valores))


def obtener_reentrenamiento(motor: Engine, id_: str) -> dict | None:
    with motor.connect() as c:
        fila = c.execute(select(reentrenamientos).where(reentrenamientos.c.id == id_)).mappings().first()
    return dict(fila) if fila else None
