"""Catálogos de prueba con la misma estructura que los archivos publicados.

Los datos reales no están en el repositorio, así que las pruebas crean sus
propios catálogos. No dependen de MLflow, de la base de datos ni de Docker.
"""

import copy
from pathlib import Path

import pytest

from novamercado.catalogos import cargar_catalogo

TIENDAS = """tienda_id,nombre,ciudad,departamento,tipo,fecha_apertura
1,NovaMercado Zona 10,Guatemala,Guatemala,hipermercado,2019-01-01
4,NovaMercado Express Zona 1,Guatemala,Guatemala,express,2019-01-01
5,NovaMercado Quetzaltenango,Quetzaltenango,Quetzaltenango,hipermercado,2019-01-01
10,NovaMercado Express Zona 16,Guatemala,Guatemala,express,2025-03-15
"""

FAMILIAS = """familia_id,nombre
abarrotes,Abarrotes
bebidas,Bebidas
lacteos,Lácteos
carnes,Carnes
panaderia,Panadería
frutas_verduras,Frutas y verduras
limpieza,Limpieza
cuidado_personal,Cuidado personal
licores,Licores
snacks,Snacks y dulces
bebe,Bebé
mascotas,Mascotas
"""

COSTOS = """familia_id,costo_faltante,costo_sobrante
abarrotes,1.0,0.2
bebidas,1.0,0.2
lacteos,1.0,1.2
carnes,1.5,2.0
panaderia,1.0,2.5
frutas_verduras,1.0,2.0
limpieza,1.0,0.1
cuidado_personal,1.0,0.1
licores,2.0,0.1
snacks,1.0,0.3
bebe,1.5,0.2
mascotas,1.0,0.2
"""

IDS = sorted(line.split(",")[0] for line in FAMILIAS.strip().splitlines()[1:])


@pytest.fixture(scope="session")
def dir_catalogos(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("publicados")
    (d / "tiendas.csv").write_text(TIENDAS, encoding="utf-8")
    (d / "familias.csv").write_text(FAMILIAS, encoding="utf-8")
    (d / "costos.csv").write_text(COSTOS, encoding="utf-8")
    return d


@pytest.fixture(scope="session")
def catalogo(dir_catalogos):
    return cargar_catalogo(dir_catalogos)


_PREDICCION = {
    "tienda_id": 5,
    "fecha": "2025-11-17",
    "familias": [{"familia_id": f, "en_promocion": 8 if f == "bebidas" else 0} for f in IDS],
}
_OBSERVACION = {
    "tienda_id": 5,
    "fecha": "2025-11-17",
    "ventas": [{"familia_id": f, "ventas": 100 + i} for i, f in enumerate(IDS)],
}


@pytest.fixture
def prediccion():
    return copy.deepcopy(_PREDICCION)


@pytest.fixture
def observacion():
    return copy.deepcopy(_OBSERVACION)


# ------------------------------------------------------------------ datos sintéticos para el modelo

FERIADOS = """fecha,nombre,tipo,ambito
2025-09-15,Independencia,feriado,nacional
2025-10-20,Revolución,feriado,nacional
2025-11-01,Todos los Santos,feriado,nacional
2025-09-30,Fin de mes,pago,nacional
2025-10-31,Fin de mes,pago,nacional
2025-11-15,Feria local,feriado,Quetzaltenango
"""


@pytest.fixture(scope="session")
def feriados(dir_catalogos):
    from novamercado.features import leer_feriados

    (dir_catalogos / "feriados.csv").write_text(FERIADOS, encoding="utf-8")
    return leer_feriados(dir_catalogos / "feriados.csv")


@pytest.fixture(scope="session")
def historico(catalogo):
    """Ventas diarias con patrón semanal, efecto de promoción y ruido, desde 2025-06-01."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    fechas = pd.date_range("2025-06-01", "2025-11-30")
    filas = []
    for tienda in catalogo.tiendas.values():
        for j, familia in enumerate(catalogo.ids_familias):
            nivel = 40 + 15 * j + 10 * tienda.tienda_id
            for fecha in fechas:
                if fecha.date() < tienda.fecha_apertura:
                    continue
                promo = int(rng.random() < 0.2) * int(rng.integers(1, 6))
                media = nivel * (1.4 if fecha.dayofweek >= 5 else 1.0) * (1 + 0.08 * promo)
                filas.append((fecha, tienda.tienda_id, familia, int(rng.poisson(media)), promo))
    return pd.DataFrame(filas, columns=["fecha", "tienda_id", "familia_id", "ventas", "en_promocion"])


@pytest.fixture(scope="session")
def params():
    return {
        "modelo": {
            "nombre_registro": "prueba-ventas", "alias_vigente": "vigente", "experimento": "prueba",
            "lgbm": {"objective": "tweedie", "learning_rate": 0.1, "num_leaves": 15, "min_data_in_leaf": 20,
                     "num_boost_round": 60, "num_threads": 1, "seed": 1},
        },
        "reentrenamiento": {"dias_calibracion": 21, "dias_evaluacion_max": 14, "dias_evaluacion_min": 7,
                            "mejora_minima_costo": 0.02, "dias_prueba_inicial": 21},
        "observaciones": {"factor_atipico": 10},
    }
