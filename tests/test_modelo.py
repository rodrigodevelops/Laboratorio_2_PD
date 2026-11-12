"""Pruebas de variables, modelos, cantidad sugerida y criterio de reemplazo."""

import numpy as np
import pandas as pd
import pytest

from novamercado.features import VARIABLES, calcular_features, tabla_entrenamiento
from novamercado.metricas import costo, formato_miles, wape
from novamercado.modelo import Pronosticador, ratio_critico
from novamercado.plausibilidad import es_atipica, maximos_historicos
from novamercado.reentrenamiento import (
    ajustar,
    combinar_ventas,
    decidir,
    entrenamiento_inicial,
    reentrenar,
    ventana_evaluacion,
)

DIA = pd.Timedelta(days=1)


def _objetivos(fecha, catalogo, promo=0):
    return pd.DataFrame(
        [(pd.Timestamp(fecha), t, f, promo) for t in catalogo.tiendas for f in catalogo.ids_familias],
        columns=["fecha", "tienda_id", "familia_id", "en_promocion"],
    )


# ------------------------------------------------------------ variables

def test_features_no_usan_el_futuro(historico, catalogo, feriados):
    """Cambiar las ventas del día D y posteriores no cambia las variables de D."""
    dia = pd.Timestamp("2025-11-10")
    objetivos = _objetivos(dia, catalogo)
    antes = calcular_features(historico, objetivos, catalogo, feriados)
    alterado = historico.copy()
    alterado.loc[alterado["fecha"] >= dia, "ventas"] = 10**6
    despues = calcular_features(alterado, objetivos, catalogo, feriados)
    pd.testing.assert_frame_equal(antes, despues)


def test_features_usan_la_venta_del_dia_anterior(historico, catalogo, feriados):
    dia = pd.Timestamp("2025-11-10")
    tabla = calcular_features(historico, _objetivos(dia, catalogo), catalogo, feriados)
    fila = tabla[(tabla["tienda_id"] == 5) & (tabla["familia_id"] == "abarrotes")].iloc[0]
    ayer = historico[(historico["tienda_id"] == 5) & (historico["familia_id"] == "abarrotes")
                     & (historico["fecha"] == dia - DIA)]
    esperado = ayer["ventas"].iloc[0]
    assert fila["lag1"] == esperado
    assert fila["dias_desde_ultima"] == 1
    assert set(VARIABLES) <= set(tabla.columns)


def test_feriado_local_solo_marca_la_ciudad(historico, catalogo, feriados):
    tabla = calcular_features(historico, _objetivos("2025-11-15", catalogo), catalogo, feriados)
    por_tienda = tabla.groupby("tienda_id")["feriado"].max()
    assert por_tienda[5] == 1  # Quetzaltenango
    assert por_tienda[1] == 0  # Guatemala


def test_features_toleran_dias_sin_observacion(historico, catalogo, feriados):
    dia = pd.Timestamp("2025-11-10")
    sin_ayer = historico[historico["fecha"] != dia - DIA]
    tabla = calcular_features(sin_ayer, _objetivos(dia, catalogo), catalogo, feriados)
    assert tabla["lag1"].isna().all()
    assert (tabla["dias_desde_ultima"] == 2).all()
    assert tabla["media7"].notna().all()


def test_prediccion_para_fecha_posterior_a_los_datos(historico, catalogo, feriados):
    tabla = calcular_features(historico, _objetivos("2025-12-05", catalogo), catalogo, feriados)
    assert tabla["lag1"].isna().all() and tabla["media28"].notna().all()


# ------------------------------------------------------------ modelos y sugerida

@pytest.fixture(scope="module")
def entrenado(historico, catalogo, feriados, params):
    return ajustar("lgbm", historico, historico, catalogo, feriados, params,
                   pd.Timestamp("2025-10-31"), pd.Timestamp("2025-11-01"), pd.Timestamp("2025-11-21"))


def test_lgbm_mejora_al_baseline(historico, catalogo, feriados, params, entrenado):
    baseline = ajustar("baseline", historico, historico, catalogo, feriados, params,
                       pd.Timestamp("2025-10-31"), pd.Timestamp("2025-11-01"), pd.Timestamp("2025-11-21"))
    prueba = tabla_entrenamiento(historico, historico, catalogo, feriados, desde="2025-11-22")
    w_lgbm = wape(prueba["ventas"], entrenado.predecir(prueba)["venta_esperada"])
    w_base = wape(prueba["ventas"], baseline.predecir(prueba)["venta_esperada"])
    assert w_lgbm < w_base


def test_sugerida_sigue_los_costos(entrenado):
    """Licores (faltar cuesta 20 veces más) se ajusta hacia arriba; panadería, hacia abajo."""
    assert entrenado.ajustes["licores"] > 0 > entrenado.ajustes["panaderia"]


def test_prediccion_cumple_el_contrato(historico, catalogo, feriados, entrenado):
    tabla = calcular_features(historico, _objetivos("2025-12-01", catalogo, promo=2), catalogo, feriados)
    pred = entrenado.predecir(tabla)
    assert len(pred) == len(tabla)
    assert pred["cantidad_sugerida"].dtype.kind == "i"
    assert (pred["cantidad_sugerida"] >= 0).all() and (pred["venta_esperada"] >= 0).all()


def test_modelo_se_guarda_y_carga_igual(historico, catalogo, feriados, entrenado, tmp_path):
    tabla = calcular_features(historico, _objetivos("2025-12-01", catalogo), catalogo, feriados)
    entrenado.guardar(tmp_path / "m")
    cargado = Pronosticador.cargar(tmp_path / "m")
    pd.testing.assert_frame_equal(entrenado.predecir(tabla), cargado.predecir(tabla))


def test_ratio_critico():
    tau = ratio_critico({"licores": (2.0, 0.1), "panaderia": (1.0, 2.5)})
    assert tau["licores"] == pytest.approx(0.952, abs=1e-3)
    assert tau["panaderia"] == pytest.approx(0.286, abs=1e-3)


def test_costo_de_negocio():
    costos = {"a": (2.0, 0.5)}
    # faltan 3 (3 × 2.0) y sobran 4 (4 × 0.5)
    assert costo([10, 6], [7, 10], ["a", "a"], costos) == pytest.approx(8.0)
    assert formato_miles(18210.4) == "18 210"


# ------------------------------------------------------------ criterio de reemplazo

def test_decidir_exige_mejora_minima():
    assert decidir(97.0, 100.0, 0.02, 10)[0] is True
    promueve, motivo = decidir(99.0, 100.0, 0.02, 10)
    assert promueve is False and "no alcanza" in motivo
    assert decidir(120.0, 100.0, 0.02, 10)[0] is False


def _predicciones(modelo, historico, catalogo, feriados, desde, hasta):
    tabla = tabla_entrenamiento(historico, historico, catalogo, feriados, desde=desde, hasta=hasta)
    pred = modelo.predecir(tabla)
    return tabla[["fecha", "tienda_id", "familia_id"]].assign(cantidad_sugerida=pred["cantidad_sugerida"].to_numpy())


def test_sin_evidencia_suficiente_no_se_reemplaza(historico, catalogo, feriados, params, entrenado):
    pred = _predicciones(entrenado, historico, catalogo, feriados, "2025-11-25", "2025-11-29")  # 5 días
    obs = historico[historico["fecha"] >= "2025-11-25"]
    r = reentrenar(historico[historico["fecha"] < "2025-11-25"], obs, obs, pred, catalogo, feriados, params)
    assert r.promovido is False and r.modelo is None and "evidencia" in r.motivo


def test_ventana_usa_solo_dias_con_prediccion_y_venta(historico, catalogo, feriados, params, entrenado):
    pred = _predicciones(entrenado, historico, catalogo, feriados, "2025-11-01", "2025-11-30")
    obs = historico[historico["fecha"].between("2025-11-10", "2025-11-30")]
    ventana = ventana_evaluacion(pred, obs, params)
    assert ventana["fecha"].nunique() == 14
    assert ventana["fecha"].min() == pd.Timestamp("2025-11-17")


def test_vigente_malo_se_reemplaza(historico, catalogo, feriados, params):
    """Si el vigente sugirió muy mal, el candidato lo reemplaza y queda listo para producción."""
    obs = historico[historico["fecha"] >= "2025-11-17"]
    malo = obs[["fecha", "tienda_id", "familia_id"]].assign(cantidad_sugerida=obs["ventas"].to_numpy() * 3)
    r = reentrenar(historico[historico["fecha"] < "2025-11-17"], obs, obs, malo, catalogo, feriados, params)
    assert r.promovido is True
    assert r.metricas["costo_candidato"] < r.metricas["costo_vigente"]
    assert r.modelo is not None and r.modelo.info["entrenado_hasta"] == "2025-11-30"


def test_vigente_bueno_no_se_reemplaza(historico, catalogo, feriados, params):
    """Si el vigente acertó exacto, ningún candidato lo puede mejorar en 2 %."""
    obs = historico[historico["fecha"] >= "2025-11-17"]
    perfecto = obs[["fecha", "tienda_id", "familia_id"]].assign(cantidad_sugerida=obs["ventas"].to_numpy())
    r = reentrenar(historico[historico["fecha"] < "2025-11-17"], obs, obs, perfecto, catalogo, feriados, params)
    assert r.promovido is False and r.modelo is None


def test_observacion_reemplaza_al_historico():
    h = pd.DataFrame({"fecha": ["2025-01-01"], "tienda_id": [1], "familia_id": ["a"], "ventas": [5]})
    o = pd.DataFrame({"fecha": ["2025-01-01"], "tienda_id": [1], "familia_id": ["a"], "ventas": [7]})
    assert combinar_ventas(h, o)["ventas"].tolist() == [7]


def test_entrenamiento_inicial(historico, catalogo, feriados, params):
    r = entrenamiento_inicial(historico, catalogo, feriados, params)
    assert r.promovido is True and r.modelo.tipo == "lgbm"
    assert r.metricas["lgbm_costo"] < r.metricas["baseline_costo"]
    assert "baseline" in r.motivo


# ------------------------------------------------------------ plausibilidad

def test_venta_atipica(historico):
    maximos = maximos_historicos(historico)
    maximo = maximos[(5, "abarrotes")]
    assert es_atipica(maximo * 11, 5, "abarrotes", maximos, 10)
    assert not es_atipica(maximo * 3, 5, "abarrotes", maximos, 10)
    assert not es_atipica(10**6, 99, "abarrotes", maximos, 10)
