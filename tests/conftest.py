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
