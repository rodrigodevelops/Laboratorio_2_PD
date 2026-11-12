"""API del servicio (FastAPI). Los endpoints solo traducen HTTP; la lógica está en ``servicio.py``.

Las solicitudes se leen como JSON libre (no con un modelo de Pydantic en la
firma del endpoint): así los datos defectuosos llegan a ``limpieza.py``, que
decide si reparar, advertir o rechazar, en lugar de que FastAPI los rechace a
todos por igual.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from novamercado.servicio import Servicio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _cuerpo(request: Request):
    contenido = await request.body()
    try:
        return json.loads(contenido) if contenido else None
    except (ValueError, UnicodeDecodeError):
        return _NO_JSON


_NO_JSON = object()


def _construir_servicio():
    """Arma el servicio real a partir de las variables de entorno."""
    from novamercado import db, registro
    from novamercado.airflow_cliente import ClienteAirflow
    from novamercado.config import cargar_params, cargar_publicados
    from novamercado.estado import GestorModelo, Monitor

    params = cargar_params()
    catalogo, historico, feriados = cargar_publicados(params)
    motor = db.crear_motor()
    db.crear_tablas(motor)
    gestor = GestorModelo(
        params["modelo"]["nombre_registro"], params["modelo"]["alias_vigente"],
        consultar_version=lambda: registro.version_vigente(params),
        descargar=lambda: registro.cargar_vigente(params),
        dir_cache=os.environ.get("NOVAMERCADO_CACHE_MODELO", "/var/lib/novamercado/modelo"),
    )
    airflow = ClienteAirflow.desde_entorno()
    monitor = Monitor(gestor, lambda: db.disponible(motor),
                      (airflow.disponible if airflow else (lambda: False)),
                      intervalo=float(os.environ.get("NOVAMERCADO_INTERVALO_MONITOR", "15")))
    return Servicio(motor, catalogo, historico, feriados, gestor, params, airflow), monitor


def crear_app(servicio: Servicio | None = None, monitor=None) -> FastAPI:
    @asynccontextmanager
    async def ciclo(app: FastAPI):
        if app.state.servicio is None:
            app.state.servicio, app.state.monitor = _construir_servicio()
            app.state.monitor.revisar()
            app.state.monitor.iniciar()
        yield
        if app.state.monitor is not None:
            app.state.monitor.detener()

    app = FastAPI(title="NovaMercado: pronóstico diario de ventas", version="1.0", lifespan=ciclo)
    app.state.servicio, app.state.monitor = servicio, monitor

    def responder(resultado: tuple[int, dict]) -> JSONResponse:
        codigo, cuerpo = resultado
        return JSONResponse(status_code=codigo, content=cuerpo)

    @app.post("/v1/prediccion")
    async def prediccion(request: Request):
        cuerpo = await _cuerpo(request)
        if cuerpo is _NO_JSON:
            return JSONResponse(status_code=422, content={"detail": "el cuerpo no es un JSON válido"})
        return responder(app.state.servicio.predecir(cuerpo))

    @app.post("/v1/observaciones")
    async def observaciones(request: Request):
        cuerpo = await _cuerpo(request)
        if cuerpo is _NO_JSON:
            return JSONResponse(status_code=422, content={"detail": "el cuerpo no es un JSON válido"})
        return responder(app.state.servicio.observar(cuerpo))

    @app.post("/admin/reentrenar")
    def reentrenar():
        return responder(app.state.servicio.reentrenar())

    @app.get("/admin/reentrenar/{id_}")
    def estado_reentrenamiento(id_: str):
        return responder(app.state.servicio.estado_reentrenamiento(id_))

    @app.get("/modelo")
    def modelo():
        return responder(app.state.servicio.modelo_vigente())

    @app.get("/health")
    def health():
        return responder(app.state.monitor.salud())

    return app


app = crear_app()
