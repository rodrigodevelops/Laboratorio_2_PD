"""Entrenamiento y criterio de reemplazo del modelo vigente (sin MLflow).

Criterio (ver DECISIONES.md):

1. Ventana de evaluación: los últimos días (hasta ``dias_evaluacion_max``) con
   predicciones registradas del modelo vigente y ventas reales conocidas.
2. El vigente se evalúa con las cantidades que **realmente entregó**: se hicieron
   antes de conocer esas ventas, así que no hay fuga de información.
3. El candidato se entrena con datos anteriores a la ventana, se calibra con los
   ``dias_calibracion`` previos y predice la ventana como lo habría hecho el
   servicio (ventas hasta el día anterior y la promoción de cada solicitud).
4. Se promueve si su costo es al menos ``mejora_minima_costo`` menor. Si gana, se
   vuelve a entrenar con todos los datos antes de registrarlo.
5. Con menos de ``dias_evaluacion_min`` días de evidencia, el vigente se mantiene.

Este módulo recibe y devuelve datos: no lee la base de datos ni usa MLflow, para
poder probarlo sin servicios.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from novamercado.catalogos import Catalogo
from novamercado.features import tabla_entrenamiento
from novamercado.metricas import costo, formato_miles, mae, wape
from novamercado.modelo import Pronosticador

LLAVES = ["fecha", "tienda_id", "familia_id"]
DIA = pd.Timedelta(days=1)


@dataclass
class Resultado:
    promovido: bool
    motivo: str
    modelo: Pronosticador | None = None
    metricas: dict = field(default_factory=dict)
    comparacion: pd.DataFrame | None = None


# ---------------------------------------------------------------- datos

def _fechas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def combinar_ventas(historico: pd.DataFrame, observaciones: pd.DataFrame) -> pd.DataFrame:
    """Histórico más observaciones; si coinciden, manda la observación."""
    partes = [_fechas(historico)[LLAVES + ["ventas"]]]
    if observaciones is not None and len(observaciones):
        partes.append(_fechas(observaciones)[LLAVES + ["ventas"]])
    ventas = pd.concat(partes, ignore_index=True)
    return ventas.drop_duplicates(LLAVES, keep="last").sort_values(LLAVES, ignore_index=True)


def combinar_promociones(historico: pd.DataFrame, solicitadas: pd.DataFrame | None) -> pd.DataFrame:
    """Promociones del histórico más las informadas en las solicitudes de pronóstico."""
    partes = [_fechas(historico)[LLAVES + ["en_promocion"]]]
    if solicitadas is not None and len(solicitadas):
        partes.append(_fechas(solicitadas)[LLAVES + ["en_promocion"]])
    promos = pd.concat(partes, ignore_index=True)
    return promos.drop_duplicates(LLAVES, keep="last")


# ---------------------------------------------------------------- entrenamiento

def ajustar(
    tipo: str, ventas, promos, catalogo: Catalogo, feriados, params: dict,
    hasta_entrenamiento, desde_calibracion, hasta_calibracion,
) -> Pronosticador:
    """Entrena con datos hasta ``hasta_entrenamiento`` y calibra en el periodo indicado."""
    modelo = Pronosticador(tipo, catalogo.costos)
    entrenamiento = tabla_entrenamiento(ventas, promos, catalogo, feriados, hasta=hasta_entrenamiento)
    modelo.entrenar(entrenamiento, params["modelo"]["lgbm"])
    calibracion = tabla_entrenamiento(
        ventas, promos, catalogo, feriados, desde=desde_calibracion, hasta=hasta_calibracion
    )
    return modelo.calibrar(calibracion)


def modelo_final(tipo: str, ventas, promos, catalogo: Catalogo, feriados, params: dict) -> Pronosticador:
    """Modelo para producción: árboles entrenados con todos los datos.

    El ajuste de la cantidad sugerida necesita errores fuera de muestra, así que
    se calcula con un modelo auxiliar entrenado sin los últimos ``dias_calibracion``
    días y evaluado en ellos; luego se copia al modelo final.
    """
    fin = pd.to_datetime(ventas["fecha"]).max()
    dias = params["reentrenamiento"]["dias_calibracion"]
    corte = fin - pd.Timedelta(days=dias)
    auxiliar = ajustar(tipo, ventas, promos, catalogo, feriados, params, corte, corte + DIA, fin)
    final = Pronosticador(tipo, catalogo.costos)
    final.entrenar(tabla_entrenamiento(ventas, promos, catalogo, feriados), params["modelo"]["lgbm"])
    final.ajustes = dict(auxiliar.ajustes)
    final.info["ajustes_calibrados_en"] = f"{(corte + DIA).date()} a {fin.date()}"
    return final


def _metricas(tabla: pd.DataFrame, pred: pd.DataFrame, costos) -> dict:
    return {
        "costo": costo(tabla["ventas"], pred["cantidad_sugerida"], tabla["familia_id"], costos),
        "wape": wape(tabla["ventas"], pred["venta_esperada"]),
        "mae": mae(tabla["ventas"], pred["venta_esperada"]),
        "filas": int(len(tabla)),
    }


def entrenamiento_inicial(historico, catalogo: Catalogo, feriados, params: dict) -> Resultado:
    """Primer modelo, al levantar el producto sin ninguno registrado.

    Se compara contra el baseline en los últimos ``dias_prueba_inicial`` días del
    histórico (reservados), como evidencia. El LightGBM se registra como vigente
    porque no hay otro modelo; se entrena de nuevo con todo el histórico.
    """
    r = params["reentrenamiento"]
    ventas = combinar_ventas(historico, None)
    promos = combinar_promociones(historico, None)
    fin = ventas["fecha"].max()
    inicio_prueba = fin - pd.Timedelta(days=r["dias_prueba_inicial"] - 1)
    fin_calibracion = inicio_prueba - DIA
    inicio_calibracion = fin_calibracion - pd.Timedelta(days=r["dias_calibracion"] - 1)
    prueba = tabla_entrenamiento(ventas, promos, catalogo, feriados, desde=inicio_prueba)

    metricas = {}
    for tipo in ("baseline", "lgbm"):
        modelo = ajustar(tipo, ventas, promos, catalogo, feriados, params,
                         inicio_calibracion - DIA, inicio_calibracion, fin_calibracion)
        for k, v in _metricas(prueba, modelo.predecir(prueba), catalogo.costos).items():
            metricas[f"{tipo}_{k}"] = v

    final = modelo_final("lgbm", ventas, promos, catalogo, feriados, params)
    ahorro = 1 - metricas["lgbm_costo"] / metricas["baseline_costo"]
    motivo = (
        f"Primer modelo. Costo en prueba {formato_miles(metricas['lgbm_costo'])} vs "
        f"{formato_miles(metricas['baseline_costo'])} del baseline ({ahorro:.1%} menos)"
    )
    metricas["periodo_prueba"] = f"{inicio_prueba.date()} a {fin.date()}"
    return Resultado(promovido=True, motivo=motivo, modelo=final, metricas=metricas)


# ---------------------------------------------------------------- criterio

def ventana_evaluacion(
    predicciones_vigente: pd.DataFrame, observaciones: pd.DataFrame, params: dict
) -> pd.DataFrame | None:
    """Predicciones del vigente con su venta real, en los últimos días disponibles."""
    if predicciones_vigente is None or observaciones is None or not len(predicciones_vigente) or not len(observaciones):
        return None
    pred = _fechas(predicciones_vigente).drop_duplicates(LLAVES, keep="last")
    obs = _fechas(observaciones)[LLAVES + ["ventas"]].drop_duplicates(LLAVES, keep="last")
    unidas = pred.merge(obs, on=LLAVES, how="inner")
    dias = sorted(unidas["fecha"].unique())[-params["reentrenamiento"]["dias_evaluacion_max"]:]
    if len(dias) < params["reentrenamiento"]["dias_evaluacion_min"]:
        return None
    return unidas[unidas["fecha"].isin(dias)].sort_values(LLAVES, ignore_index=True)


def decidir(costo_candidato: float, costo_vigente: float, mejora_minima: float, dias: int) -> tuple[bool, str]:
    base = (
        f"Costo en validación {formato_miles(costo_candidato)} vs "
        f"{formato_miles(costo_vigente)} del vigente ({dias} días)"
    )
    mejora = 1 - costo_candidato / costo_vigente if costo_vigente > 0 else 0.0
    if mejora >= mejora_minima:
        return True, f"{base}: {mejora:.1%} menos"
    return False, f"{base}: no alcanza la mejora mínima de {mejora_minima:.0%}"


def reentrenar(
    historico, observaciones, promos_solicitadas, predicciones_vigente,
    catalogo: Catalogo, feriados, params: dict,
) -> Resultado:
    r = params["reentrenamiento"]
    ventana = ventana_evaluacion(predicciones_vigente, observaciones, params)
    if ventana is None:
        return Resultado(
            promovido=False,
            motivo=(
                f"Sin evidencia suficiente: el vigente necesita al menos {r['dias_evaluacion_min']} días "
                "con predicciones registradas y ventas reales para compararse"
            ),
        )

    ventas = combinar_ventas(historico, observaciones)
    promos = combinar_promociones(historico, promos_solicitadas)
    inicio = ventana["fecha"].min()
    fin_calibracion = inicio - DIA
    inicio_calibracion = fin_calibracion - pd.Timedelta(days=r["dias_calibracion"] - 1)
    candidato = ajustar("lgbm", ventas, promos, catalogo, feriados, params,
                        inicio_calibracion - DIA, inicio_calibracion, fin_calibracion)

    evaluacion = tabla_entrenamiento(ventas, promos, catalogo, feriados, desde=inicio, hasta=ventana["fecha"].max())
    evaluacion = evaluacion.merge(ventana[LLAVES + ["cantidad_sugerida"]], on=LLAVES, how="inner")
    pred = candidato.predecir(evaluacion)
    costo_candidato = costo(evaluacion["ventas"], pred["cantidad_sugerida"], evaluacion["familia_id"], catalogo.costos)
    costo_vigente = costo(evaluacion["ventas"], evaluacion["cantidad_sugerida"], evaluacion["familia_id"], catalogo.costos)
    dias = int(evaluacion["fecha"].nunique())
    promovido, motivo = decidir(costo_candidato, costo_vigente, r["mejora_minima_costo"], dias)

    metricas = {
        "costo_candidato": costo_candidato,
        "costo_vigente": costo_vigente,
        "wape_candidato": wape(evaluacion["ventas"], pred["venta_esperada"]),
        "dias_evaluacion": dias,
        "filas_evaluacion": int(len(evaluacion)),
        "periodo_evaluacion": f"{inicio.date()} a {ventana['fecha'].max().date()}",
    }
    comparacion = evaluacion[LLAVES + ["ventas"]].assign(
        sugerida_candidato=pred["cantidad_sugerida"].to_numpy(),
        sugerida_vigente=evaluacion["cantidad_sugerida"].to_numpy(),
    )
    modelo = modelo_final("lgbm", ventas, promos, catalogo, feriados, params) if promovido else None
    return Resultado(promovido, motivo, modelo, metricas, comparacion)
