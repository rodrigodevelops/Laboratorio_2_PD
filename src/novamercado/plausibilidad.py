"""Control de valores absurdos en las ventas reales.

La limpieza revisa el formato; este módulo revisa si el valor es plausible. Una
venta mayor que ``factor_atipico`` veces el máximo histórico de esa tienda y
familia se guarda marcada como dudosa y no se usa para entrenar. El umbral es
amplio a propósito: un cambio real de demanda no multiplica las ventas por diez
de un día para otro, pero un cero de más sí.
"""

from __future__ import annotations

import pandas as pd


def maximos_historicos(historico: pd.DataFrame) -> dict[tuple[int, str], float]:
    maximos = historico.groupby(["tienda_id", "familia_id"])["ventas"].max()
    return {(int(t), str(f)): float(v) for (t, f), v in maximos.items()}


def es_atipica(ventas: float, tienda_id: int, familia_id: str, maximos: dict, factor: float) -> bool:
    """Sin máximo histórico conocido (o máximo 0) no se marca nada."""
    maximo = maximos.get((tienda_id, familia_id))
    return bool(maximo) and ventas > factor * maximo
