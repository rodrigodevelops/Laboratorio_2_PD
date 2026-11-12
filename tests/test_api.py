"""Pruebas del contrato de la API, sin MLflow, sin Airflow y con SQLite en lugar de PostgreSQL."""

import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from novamercado import db
from novamercado.airflow_cliente import AirflowNoDisponible
from novamercado.api import crear_app
from novamercado.estado import GestorModelo, Monitor
from novamercado.reentrenamiento import ajustar
from novamercado.servicio import Servicio

FECHA = "2025-12-01"


class AirflowFalso:
    def __init__(self):
        self.disparados, self.estados, self.caido = [], {}, False

    def disparar(self, run_id):
        if self.caido:
            raise AirflowNoDisponible("sin conexión")
        self.disparados.append(run_id)
        self.estados[run_id] = "running"

    def estado(self, run_id):
        return self.estados.get(run_id)

    def disponible(self):
        return not self.caido


class MlflowFalso:
    """Simula el Model Registry: versiones disponibles y si el servidor responde."""

    def __init__(self, modelo):
        self.modelos = {"1": modelo}
        self.vigente = "1"
        self.caido = False

    def version(self):
        if self.caido:
            raise ConnectionError("MLflow no responde")
        return self.vigente

    def descargar(self):
        if self.caido:
            raise ConnectionError("MLflow no responde")
        return self.modelos[self.vigente], self.vigente


@pytest.fixture(scope="module")
def modelo(historico, catalogo, feriados, params):
    return ajustar("lgbm", historico, historico, catalogo, feriados, params,
                   pd.Timestamp("2025-10-31"), pd.Timestamp("2025-11-01"), pd.Timestamp("2025-11-30"))


@pytest.fixture
def entorno(tmp_path, modelo, historico, catalogo, feriados, params):
    motor = db.crear_motor(f"sqlite:///{tmp_path / 'producto.db'}")
    db.crear_tablas(motor)
    mlflow = MlflowFalso(modelo)
    gestor = GestorModelo("novamercado-ventas", "vigente", mlflow.version, mlflow.descargar, tmp_path / "cache")
    airflow = AirflowFalso()
    monitor = Monitor(gestor, lambda: db.disponible(motor), airflow.disponible)
    monitor.revisar()
    servicio = Servicio(motor, catalogo, historico, feriados, gestor, params, airflow)
    cliente = TestClient(crear_app(servicio, monitor))
    return {"cliente": cliente, "motor": motor, "mlflow": mlflow, "airflow": airflow,
            "monitor": monitor, "gestor": gestor}


def _contar(motor, tabla):
    with motor.connect() as c:
        return c.execute(select(func.count()).select_from(tabla)).scalar()


@pytest.fixture
def pedido(prediccion):
    p = copy.deepcopy(prediccion)
    p["fecha"] = FECHA
    return p


@pytest.fixture
def venta(observacion):
    o = copy.deepcopy(observacion)
    o["fecha"] = "2025-11-30"
    return o


# ------------------------------------------------------------ predicción

def test_prediccion_valida_cumple_el_contrato(entorno, pedido):
    r = entorno["cliente"].post("/v1/prediccion", json=pedido)
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) >= {"tienda_id", "fecha", "version_modelo", "predicciones", "calidad"}
    assert cuerpo["tienda_id"] == 5 and cuerpo["fecha"] == FECHA
    assert cuerpo["version_modelo"] == "1" and isinstance(cuerpo["version_modelo"], str)
    assert cuerpo["calidad"] == {"estado": "ok", "observaciones": []}
    assert len(cuerpo["predicciones"]) == 12
    for p in cuerpo["predicciones"]:
        assert set(p) >= {"familia_id", "venta_esperada", "cantidad_sugerida"}
        assert isinstance(p["cantidad_sugerida"], int) and p["cantidad_sugerida"] >= 0


def test_prediccion_reparada_informa_la_correccion(entorno, pedido):
    pedido["tienda_id"] = "T05"
    pedido["familias"][6]["familia_id"] = "LÁCTEOS"
    cuerpo = entorno["cliente"].post("/v1/prediccion", json=pedido).json()
    assert cuerpo["calidad"]["estado"] == "corregido"
    campos = {o["campo"]: o["accion"] for o in cuerpo["calidad"]["observaciones"]}
    assert campos == {"tienda_id": "reparar", "familias[6].familia_id": "reparar"}


def test_prediccion_con_supuestos_es_advertencia(entorno, pedido):
    pedido["familias"] = pedido["familias"][:10]
    cuerpo = entorno["cliente"].post("/v1/prediccion", json=pedido).json()
    assert cuerpo["calidad"]["estado"] == "advertencia"
    assert len(cuerpo["predicciones"]) == 12


@pytest.mark.parametrize("cambio", [{"tienda_id": 99}, {"fecha": "05/11/2025"}, {"familias": []}])
def test_rechazo_responde_422_con_detail(entorno, pedido, cambio):
    pedido.update(cambio)
    r = entorno["cliente"].post("/v1/prediccion", json=pedido)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


@pytest.mark.parametrize("contenido", [b"{no es json", b"", b"[1, 2]"])
def test_cuerpo_invalido_responde_422(entorno, contenido):
    r = entorno["cliente"].post("/v1/prediccion", content=contenido, headers={"content-type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()


def test_cada_solicitud_queda_registrada(entorno, pedido):
    cliente, motor = entorno["cliente"], entorno["motor"]
    cliente.post("/v1/prediccion", json=pedido)
    cliente.post("/v1/prediccion", json=pedido)  # la misma fecha dos veces es válido
    pedido["tienda_id"] = 99
    cliente.post("/v1/prediccion", json=pedido)
    with motor.connect() as c:
        estados = [r.estado for r in c.execute(select(db.solicitudes.c.estado))]
        versiones = {r.version_modelo for r in c.execute(select(db.predicciones.c.version_modelo))}
    assert estados == ["ok", "ok", "rechazada"]
    assert _contar(motor, db.predicciones) == 24 and versiones == {"1"}


def test_las_correcciones_quedan_registradas(entorno, pedido):
    pedido["tienda_id"] = "T05"
    entorno["cliente"].post("/v1/prediccion", json=pedido)
    with entorno["motor"].connect() as c:
        fila = c.execute(select(db.correcciones)).mappings().one()
    assert fila["campo"] == "tienda_id" and fila["accion"] == "reparar"


def test_la_prediccion_usa_las_observaciones_registradas(entorno, pedido, venta):
    cliente = entorno["cliente"]
    antes = {p["familia_id"]: p["venta_esperada"] for p in cliente.post("/v1/prediccion", json=pedido).json()["predicciones"]}
    for v in venta["ventas"]:
        v["ventas"] = 5
    cliente.post("/v1/observaciones", json=venta)
    despues = {p["familia_id"]: p["venta_esperada"] for p in cliente.post("/v1/prediccion", json=pedido).json()["predicciones"]}
    assert antes != despues


# ------------------------------------------------------------ observaciones

def test_observacion_es_idempotente(entorno, venta):
    cliente, motor = entorno["cliente"], entorno["motor"]
    primera = cliente.post("/v1/observaciones", json=venta).json()
    assert primera == {"registros_guardados": 12, "calidad": {"estado": "ok", "observaciones": []}}
    assert cliente.post("/v1/observaciones", json=venta).json()["registros_guardados"] == 0
    assert _contar(motor, db.observaciones) == 12


def test_observacion_modificada_reemplaza_y_queda_en_el_historial(entorno, venta):
    cliente, motor = entorno["cliente"], entorno["motor"]
    cliente.post("/v1/observaciones", json=venta)
    venta["ventas"][0]["ventas"] += 10
    assert cliente.post("/v1/observaciones", json=venta).json()["registros_guardados"] == 1
    assert _contar(motor, db.observaciones) == 12
    assert _contar(motor, db.observaciones_historial) == 13


def test_ventas_negativas_no_se_guardan(entorno, venta):
    venta["ventas"][3]["ventas"] = -4
    cuerpo = entorno["cliente"].post("/v1/observaciones", json=venta).json()
    assert cuerpo["registros_guardados"] == 11 and cuerpo["calidad"]["estado"] == "advertencia"


def test_venta_atipica_se_guarda_pero_no_se_usa_para_entrenar(entorno, venta):
    venta["ventas"][0]["ventas"] = 10**7
    cuerpo = entorno["cliente"].post("/v1/observaciones", json=venta).json()
    assert cuerpo["registros_guardados"] == 12 and cuerpo["calidad"]["estado"] == "advertencia"
    datos = db.datos_reentrenamiento(entorno["motor"], "1")
    assert len(datos["observaciones"]) == 11


def test_observacion_rechazada_responde_422(entorno, venta):
    venta["tienda_id"] = "Zona 10"
    assert entorno["cliente"].post("/v1/observaciones", json=venta).status_code == 422


def test_datos_para_reentrenar(entorno, pedido, venta):
    cliente = entorno["cliente"]
    venta["fecha"] = FECHA
    cliente.post("/v1/prediccion", json=pedido)
    pedido["familias"][0]["en_promocion"] = 4
    cliente.post("/v1/prediccion", json=pedido)  # gana la última solicitud
    cliente.post("/v1/observaciones", json=venta)
    datos = db.datos_reentrenamiento(entorno["motor"], "1")
    assert len(datos["predicciones_vigente"]) == 12 and len(datos["observaciones"]) == 12
    promo = datos["promociones"].set_index("familia_id")["en_promocion"]
    assert promo[pedido["familias"][0]["familia_id"]] == 4
    assert len(db.datos_reentrenamiento(entorno["motor"], "2")["predicciones_vigente"]) == 0


# ------------------------------------------------------------ modelo vigente y salud

def test_modelo_y_salud(entorno):
    cliente = entorno["cliente"]
    assert cliente.get("/modelo").json() == {"nombre": "novamercado-ventas", "alias": "vigente", "version": "1"}
    r = cliente.get("/health")
    assert r.status_code == 200 and r.json()["estado"] == "ok"


def test_mlflow_caido_sigue_prediciendo_y_salud_degradada(entorno, pedido):
    entorno["mlflow"].caido = True
    entorno["monitor"].revisar()
    r = entorno["cliente"].get("/health")
    assert r.status_code == 200 and r.json()["estado"] == "degradado" and "MLflow" in r.json()["motivo"]
    assert entorno["cliente"].post("/v1/prediccion", json=pedido).status_code == 200
    entorno["mlflow"].caido = False
    entorno["monitor"].revisar()
    assert entorno["cliente"].get("/health").json()["estado"] == "ok"


def test_modelo_nuevo_se_usa_sin_reiniciar(entorno, pedido, modelo):
    entorno["mlflow"].modelos["2"] = modelo
    entorno["mlflow"].vigente = "2"
    entorno["monitor"].revisar()
    assert entorno["cliente"].post("/v1/prediccion", json=pedido).json()["version_modelo"] == "2"
    assert entorno["cliente"].get("/modelo").json()["version"] == "2"


def test_sin_modelo_salud_responde_503(tmp_path, historico, catalogo, feriados, params):
    gestor = GestorModelo("n", "vigente", lambda: None, lambda: None)
    motor = db.crear_motor(f"sqlite:///{tmp_path / 'p.db'}")
    db.crear_tablas(motor)
    monitor = Monitor(gestor, lambda: True, lambda: True)
    monitor.revisar()
    cliente = TestClient(crear_app(Servicio(motor, catalogo, historico, feriados, gestor, params), monitor))
    assert cliente.get("/health").status_code == 503
    assert cliente.get("/modelo").status_code == 503


def test_arranque_con_mlflow_caido_usa_la_copia_local(entorno, tmp_path):
    """El gestor guardó una copia al cargar la versión 1; otro gestor la recupera sin MLflow."""
    def caido():
        raise ConnectionError("MLflow no responde")

    nuevo = GestorModelo("n", "vigente", caido, caido, tmp_path / "cache")
    assert nuevo.refrescar() is False
    assert nuevo.cargado and nuevo.version == "1"


# ------------------------------------------------------------ reentrenamiento

def test_reentrenamiento_ciclo_completo(entorno):
    cliente, motor, airflow = entorno["cliente"], entorno["motor"], entorno["airflow"]
    r = cliente.post("/admin/reentrenar")
    assert r.status_code == 202 and isinstance(r.json()["id"], str)
    id_ = r.json()["id"]
    assert airflow.disparados == [id_]
    assert cliente.get(f"/admin/reentrenar/{id_}").json() == {"estado": "en_curso"}

    # El DAG registra su resultado al terminar.
    db.actualizar_reentrenamiento(motor, id_, estado="exitoso", promovido=True, version="2",
                                  motivo="Costo en validación 18 210 vs 19 940 del vigente")
    assert cliente.get(f"/admin/reentrenar/{id_}").json() == {
        "estado": "exitoso", "promovido": True, "version": "2",
        "motivo": "Costo en validación 18 210 vs 19 940 del vigente",
    }


def test_reentrenamiento_fallido_en_airflow(entorno):
    cliente, airflow = entorno["cliente"], entorno["airflow"]
    id_ = cliente.post("/admin/reentrenar").json()["id"]
    airflow.estados[id_] = "failed"
    cuerpo = cliente.get(f"/admin/reentrenar/{id_}").json()
    assert cuerpo["estado"] == "fallido" and cuerpo["promovido"] is False and cuerpo["version"] == "1"


def test_reentrenamiento_sin_airflow_responde_503(entorno):
    entorno["airflow"].caido = True
    assert entorno["cliente"].post("/admin/reentrenar").status_code == 503


def test_reentrenamiento_desconocido_responde_404(entorno):
    assert entorno["cliente"].get("/admin/reentrenar/no-existe").status_code == 404
