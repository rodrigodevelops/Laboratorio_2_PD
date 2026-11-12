"""Lógica de los endpoints. La API (``api.py``) solo traduce HTTP a estas llamadas.

Cada método devuelve ``(código HTTP, cuerpo)``.
"""

from __future__ import annotations

import logging
import uuid

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from novamercado import db
from novamercado.airflow_cliente import AirflowNoDisponible, ClienteAirflow
from novamercado.catalogos import Catalogo
from novamercado.esquemas import (
    Calidad,
    EstadoReentrenamiento,
    ObservacionCalidad,
    PrediccionFamilia,
    RespuestaObservaciones,
    RespuestaPrediccion,
)
from novamercado.estado import GestorModelo
from novamercado.features import DIAS_HISTORIA, calcular_features
from novamercado.limpieza import Rechazo, limpiar_observaciones, limpiar_prediccion
from novamercado.plausibilidad import es_atipica, maximos_historicos

log = logging.getLogger("novamercado")


class Servicio:
    def __init__(self, motor: Engine, catalogo: Catalogo, historico: pd.DataFrame, feriados: pd.DataFrame,
                 gestor: GestorModelo, params: dict, airflow: ClienteAirflow | None = None):
        self.motor, self.catalogo, self.feriados = motor, catalogo, feriados
        self.historico = historico.copy()
        self.historico["fecha"] = pd.to_datetime(self.historico["fecha"])
        self.gestor, self.params, self.airflow = gestor, params, airflow
        self.maximos = maximos_historicos(self.historico)
        self.factor_atipico = params["observaciones"]["factor_atipico"]

    # ------------------------------------------------------------ predicción

    def _historia(self, tienda_id: int, fecha) -> pd.DataFrame:
        desde = pd.Timestamp(fecha) - pd.Timedelta(days=DIAS_HISTORIA)
        hasta = pd.Timestamp(fecha) - pd.Timedelta(days=1)
        h = self.historico
        base = h[(h["tienda_id"] == tienda_id) & (h["fecha"] >= desde) & (h["fecha"] <= hasta)]
        base = base[["fecha", "tienda_id", "familia_id", "ventas"]]
        try:
            obs = db.observaciones_tienda(self.motor, tienda_id, desde.date(), hasta.date())
        except Exception as e:
            log.warning("No se pudieron leer observaciones; se usa solo el histórico: %s", e)
            obs = base.iloc[:0]
        if len(obs):
            obs = obs.assign(fecha=pd.to_datetime(obs["fecha"]))
            base = pd.concat([base, obs], ignore_index=True).drop_duplicates(
                ["fecha", "tienda_id", "familia_id"], keep="last")
        return base

    def predecir(self, cuerpo) -> tuple[int, dict]:
        try:
            solicitud, calidad = limpiar_prediccion(cuerpo, self.catalogo)
        except Rechazo as e:
            self._registrar("prediccion", cuerpo, "rechazada", detalle=e.detalle)
            return 422, {"detail": e.detalle}

        modelo, version = self.gestor.actual()
        if modelo is None:
            self._registrar("prediccion", cuerpo, "error", solicitud.tienda_id, solicitud.fecha,
                            detalle="sin modelo cargado")
            return 503, {"detail": "el servicio todavía no tiene un modelo cargado"}

        objetivos = pd.DataFrame([
            {"fecha": pd.Timestamp(solicitud.fecha), "tienda_id": solicitud.tienda_id,
             "familia_id": f.familia_id, "en_promocion": f.en_promocion}
            for f in solicitud.familias
        ])
        tabla = calcular_features(self._historia(solicitud.tienda_id, solicitud.fecha), objetivos,
                                  self.catalogo, self.feriados, tiendas=[solicitud.tienda_id])
        pred = modelo.predecir(tabla)
        promos = {f.familia_id: f.en_promocion for f in solicitud.familias}
        filas = [
            {"familia_id": r.familia_id, "en_promocion": promos[r.familia_id],
             "venta_esperada": float(r.venta_esperada), "cantidad_sugerida": int(r.cantidad_sugerida)}
            for r in pred.itertuples(index=False)
        ]
        respuesta = RespuestaPrediccion(
            tienda_id=solicitud.tienda_id,
            fecha=solicitud.fecha,
            version_modelo=version,
            predicciones=[PrediccionFamilia(**{k: f[k] for k in ("familia_id", "venta_esperada", "cantidad_sugerida")})
                          for f in filas],
            calidad=Calidad.desde(calidad),
        )
        try:
            with self.motor.begin() as con:
                id_ = db.registrar_solicitud(con, "prediccion", cuerpo, respuesta.calidad.estado,
                                             solicitud.tienda_id, solicitud.fecha, version=version, calidad=calidad)
                db.registrar_predicciones(con, id_, solicitud.tienda_id, solicitud.fecha, filas, version)
        except Exception as e:  # se responde igual: la tienda necesita su pronóstico
            log.error("No se pudo registrar la predicción: %s", e)
        return 200, respuesta.model_dump(mode="json")

    # ------------------------------------------------------------ observaciones

    def observar(self, cuerpo) -> tuple[int, dict]:
        try:
            solicitud, calidad = limpiar_observaciones(cuerpo, self.catalogo)
        except Rechazo as e:
            self._registrar("observaciones", cuerpo, "rechazada", detalle=e.detalle)
            return 422, {"detail": e.detalle}

        calidad = list(calidad)
        ventas = []
        for v in solicitud.ventas:
            atipica = es_atipica(v.ventas, solicitud.tienda_id, v.familia_id, self.maximos, self.factor_atipico)
            if atipica:
                maximo = self.maximos[(solicitud.tienda_id, v.familia_id)]
                calidad.append(ObservacionCalidad(
                    campo=f"ventas.{v.familia_id}", accion="advertir",
                    detalle=f"{v.ventas:.0f} supera {self.factor_atipico} veces el máximo histórico ({maximo:.0f}); "
                            "se guardó como dudosa y no se usará para entrenar",
                ))
            ventas.append({"familia_id": v.familia_id, "ventas": v.ventas, "atipica": atipica})

        estado = Calidad.desde(calidad)
        for intento in range(2):  # dos envíos idénticos simultáneos: el segundo reintenta
            try:
                with self.motor.begin() as con:
                    id_ = db.registrar_solicitud(con, "observaciones", cuerpo, estado.estado,
                                                 solicitud.tienda_id, solicitud.fecha, calidad=calidad)
                    guardados = db.guardar_observaciones(con, id_, solicitud.tienda_id, solicitud.fecha, ventas)
                break
            except IntegrityError:
                if intento:
                    raise
            except Exception as e:
                log.error("No se pudieron guardar las observaciones: %s", e)
                return 503, {"detail": "la base de datos no está disponible; reintente más tarde"}
        return 200, RespuestaObservaciones(registros_guardados=guardados, calidad=estado).model_dump(mode="json")

    def _registrar(self, endpoint, cuerpo, estado, tienda_id=None, fecha=None, detalle=None) -> None:
        try:
            with self.motor.begin() as con:
                db.registrar_solicitud(con, endpoint, cuerpo, estado, tienda_id, fecha, detalle=detalle)
        except Exception as e:
            log.error("No se pudo registrar la solicitud: %s", e)

    # ------------------------------------------------------------ modelo y reentrenamiento

    def modelo_vigente(self) -> tuple[int, dict]:
        _, version = self.gestor.actual()
        if version is None:
            return 503, {"detail": "todavía no hay un modelo cargado"}
        return 200, {"nombre": self.gestor.nombre, "alias": self.gestor.alias, "version": version}

    def reentrenar(self) -> tuple[int, dict]:
        if self.airflow is None:
            return 503, {"detail": "Airflow no está configurado"}
        id_ = f"reentrenar_{uuid.uuid4().hex[:12]}"
        try:
            db.crear_reentrenamiento(self.motor, id_)
        except Exception:
            return 503, {"detail": "la base de datos no está disponible"}
        try:
            self.airflow.disparar(id_)
        except AirflowNoDisponible as e:
            db.actualizar_reentrenamiento(self.motor, id_, estado="fallido", promovido=False,
                                          version=self.gestor.version, motivo=f"no se pudo iniciar: {e}")
            return 503, {"detail": "no se pudo iniciar el reentrenamiento: Airflow no está disponible"}
        return 202, {"id": id_}

    def estado_reentrenamiento(self, id_: str) -> tuple[int, dict]:
        try:
            fila = db.obtener_reentrenamiento(self.motor, id_)
        except Exception:
            return 503, {"detail": "la base de datos no está disponible"}
        if fila is None:
            return 404, {"detail": f"no existe el reentrenamiento '{id_}'"}
        if fila["estado"] == "en_curso" and self.airflow is not None:
            try:
                estado_airflow = self.airflow.estado(id_)
            except AirflowNoDisponible:
                estado_airflow = None
            if estado_airflow == "failed":
                # El DAG no llegó a registrar su resultado: falló antes de decidir.
                fila.update(estado="fallido", promovido=False, version=self.gestor.version,
                            motivo="La ejecución falló en Airflow; el modelo vigente no cambió")
                db.actualizar_reentrenamiento(self.motor, id_, **{k: fila[k] for k in
                                                                  ("estado", "promovido", "version", "motivo")})
        if fila["estado"] == "en_curso":
            return 200, EstadoReentrenamiento(estado="en_curso").model_dump(exclude_none=True)
        return 200, EstadoReentrenamiento(
            estado=fila["estado"], promovido=bool(fila["promovido"]),
            version=fila["version"] or self.gestor.version, motivo=fila["motivo"] or "",
        ).model_dump()

