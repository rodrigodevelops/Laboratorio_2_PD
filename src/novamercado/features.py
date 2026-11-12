"""Variables del modelo, calculadas solo con información disponible al predecir.

Para el día D se usan las ventas hasta D−1, la promoción del día D (llega en la
solicitud) y el calendario. Todas las ventas pasan por ``shift(1)`` sobre una
grilla diaria completa, así que la venta del propio día D nunca entra en sus
variables, aunque esté en la historia que se pasa. La prueba
``test_features_no_usan_el_futuro`` lo verifica.

Los días sin observación quedan vacíos (NaN); LightGBM los maneja.
"""

from __future__ import annotations

import pandas as pd

from novamercado.catalogos import Catalogo

TIPOS_CALENDARIO = ("feriado", "comercial", "pago", "medio_dia")
VARIABLES = [
    "tienda_id", "familia", "formato", "en_promocion",
    "lag1", "lag7", "lag14", "media7", "media28", "media_dia_semana",
    "dias_desde_ultima", "dia_semana", "dia_mes", "mes",
    *TIPOS_CALENDARIO,
]
CATEGORICAS = ["familia", "formato"]
DIAS_HISTORIA = 35  # lo máximo que miran las variables hacia atrás (28 días + margen)


def leer_feriados(ruta) -> pd.DataFrame:
    f = pd.read_csv(ruta, parse_dates=["fecha"])
    f["ambito"] = f["ambito"].astype(str)
    return f


def _calendario(fechas: pd.DatetimeIndex, catalogo: Catalogo, feriados: pd.DataFrame,
                tiendas: list[int] | None = None) -> pd.DataFrame:
    """Marca, por tienda y fecha, feriados y fechas especiales según la ciudad."""
    filas = []
    for tienda in catalogo.tiendas.values():
        if tiendas and tienda.tienda_id not in tiendas:
            continue
        base = pd.DataFrame({"tienda_id": tienda.tienda_id, "fecha": fechas})
        for tipo in TIPOS_CALENDARIO:
            sub = feriados[(feriados["tipo"] == tipo) & (
                (feriados["ambito"] == "nacional") | (feriados["ambito"] == tienda.ciudad)
            )]
            base[tipo] = base["fecha"].isin(set(sub["fecha"])).astype(int)
        filas.append(base)
    return pd.concat(filas, ignore_index=True)


def calcular_features(
    historia: pd.DataFrame,
    objetivos: pd.DataFrame,
    catalogo: Catalogo,
    feriados: pd.DataFrame,
    tiendas: list[int] | None = None,
) -> pd.DataFrame:
    """Devuelve ``objetivos`` con las variables del modelo.

    ``tiendas`` limita los cálculos a esas tiendas (más rápido al servir una
    solicitud); las categorías se toman siempre del catálogo completo.

    - ``historia``: ventas conocidas (``fecha, tienda_id, familia_id, ventas``).
    - ``objetivos``: filas a predecir (``fecha, tienda_id, familia_id, en_promocion``);
      ``en_promocion`` puede ser NaN si no se conoce.
    """
    objetivos = objetivos.copy()
    objetivos["fecha"] = pd.to_datetime(objetivos["fecha"])
    historia = historia[["fecha", "tienda_id", "familia_id", "ventas"]].copy()
    historia["fecha"] = pd.to_datetime(historia["fecha"])

    inicio = objetivos["fecha"].min() - pd.Timedelta(days=DIAS_HISTORIA)
    historia = historia[(historia["fecha"] >= inicio) & (historia["fecha"] <= objetivos["fecha"].max())]
    fechas = pd.date_range(inicio, objetivos["fecha"].max(), freq="D")

    grilla = pd.MultiIndex.from_product(
        [sorted(tiendas or catalogo.tiendas), catalogo.ids_familias, fechas],
        names=["tienda_id", "familia_id", "fecha"],
    ).to_frame(index=False)
    grilla = grilla.merge(
        historia.groupby(["tienda_id", "familia_id", "fecha"], as_index=False)["ventas"].last(),
        on=["tienda_id", "familia_id", "fecha"], how="left",
    )
    grilla = grilla.sort_values(["tienda_id", "familia_id", "fecha"], ignore_index=True)

    serie = grilla.groupby(["tienda_id", "familia_id"], sort=False)["ventas"]
    previa = serie.shift(1)  # solo información hasta D−1
    claves = [grilla["tienda_id"], grilla["familia_id"]]
    grilla["lag1"] = previa
    grilla["lag7"] = serie.shift(7)
    grilla["lag14"] = serie.shift(14)
    grilla["media7"] = previa.groupby(claves).transform(lambda x: x.rolling(7, min_periods=1).mean())
    grilla["media28"] = previa.groupby(claves).transform(lambda x: x.rolling(28, min_periods=1).mean())
    mismos = [serie.shift(k) for k in (7, 14, 21, 28)]
    grilla["media_dia_semana"] = pd.concat(mismos, axis=1).mean(axis=1, skipna=True)

    # Días desde la última venta conocida antes de D (se agranda si faltan observaciones).
    conocida = grilla["fecha"].where(grilla["ventas"].notna())
    ultima = conocida.groupby(claves).transform(lambda x: x.ffill().shift(1))
    grilla["dias_desde_ultima"] = (grilla["fecha"] - ultima).dt.days

    calendario = _calendario(fechas, catalogo, feriados, tiendas)
    grilla = grilla.merge(calendario, on=["tienda_id", "fecha"], how="left")

    columnas = ["tienda_id", "familia_id", "fecha", "lag1", "lag7", "lag14", "media7", "media28",
                "media_dia_semana", "dias_desde_ultima", *TIPOS_CALENDARIO]
    salida = objetivos.merge(grilla[columnas], on=["tienda_id", "familia_id", "fecha"], how="left")
    salida["dia_semana"] = salida["fecha"].dt.dayofweek
    salida["dia_mes"] = salida["fecha"].dt.day
    salida["mes"] = salida["fecha"].dt.month
    salida["formato"] = salida["tienda_id"].map({t: v.tipo for t, v in catalogo.tiendas.items()})
    salida["familia"] = salida["familia_id"]
    salida["en_promocion"] = pd.to_numeric(salida["en_promocion"], errors="coerce").astype(float)
    for col in CATEGORICAS:
        salida[col] = pd.Categorical(salida[col], categories=_categorias(col, catalogo))
    return salida


def _categorias(col: str, catalogo: Catalogo) -> list[str]:
    if col == "familia":
        return catalogo.ids_familias
    return sorted({t.tipo for t in catalogo.tiendas.values()})


def matriz(df: pd.DataFrame) -> pd.DataFrame:
    return df[VARIABLES]


def tabla_entrenamiento(
    ventas: pd.DataFrame, promociones: pd.DataFrame, catalogo: Catalogo, feriados: pd.DataFrame,
    desde=None, hasta=None,
) -> pd.DataFrame:
    """Filas con venta conocida entre ``desde`` y ``hasta``, con sus variables y ``ventas``.

    ``promociones`` trae ``en_promocion`` por fecha, tienda y familia (del histórico
    o de las solicitudes de pronóstico); si falta, queda NaN.
    """
    ventas = ventas.copy()
    ventas["fecha"] = pd.to_datetime(ventas["fecha"])
    sel = ventas
    if desde is not None:
        sel = sel[sel["fecha"] >= pd.Timestamp(desde)]
    if hasta is not None:
        sel = sel[sel["fecha"] <= pd.Timestamp(hasta)]
    objetivos = sel[["fecha", "tienda_id", "familia_id", "ventas"]]
    promos = promociones.copy()
    promos["fecha"] = pd.to_datetime(promos["fecha"])
    promos = promos.drop_duplicates(["fecha", "tienda_id", "familia_id"], keep="last")
    objetivos = objetivos.merge(
        promos[["fecha", "tienda_id", "familia_id", "en_promocion"]],
        on=["fecha", "tienda_id", "familia_id"], how="left",
    )
    tabla = calcular_features(ventas, objetivos.drop(columns="ventas"), catalogo, feriados)
    tabla["ventas"] = objetivos["ventas"].to_numpy()
    return tabla[tabla["ventas"].notna()].reset_index(drop=True)

