"""Pruebas de la política ante datos defectuosos.

Cubren los ejemplos del catálogo (E01 a E10) y variantes que no están en él,
porque el servicio debe aplicar reglas generales.
"""

from datetime import date

import pytest

from novamercado.esquemas import Calidad
from novamercado.limpieza import (
    Rechazo,
    a_numero,
    limpiar_observaciones,
    limpiar_prediccion,
    resolver_familia,
)


def _acciones(obs):
    return [(o.campo, o.accion) for o in obs]


def _promos(solicitud):
    return {f.familia_id: f.en_promocion for f in solicitud.familias}


# ------------------------------------------------------------ solicitud válida

def test_prediccion_valida_sin_observaciones(catalogo, prediccion):
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert obs == []
    assert Calidad.desde(obs).estado == "ok"
    assert solicitud.tienda_id == 5 and solicitud.fecha == date(2025, 11, 17)
    assert _promos(solicitud)["bebidas"] == 8
    assert len(solicitud.familias) == 12


def test_observacion_valida_sin_observaciones(catalogo, observacion):
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    assert obs == [] and len(solicitud.ventas) == 12


# ------------------------------------------------------------ E01 tienda

@pytest.mark.parametrize(
    "valor",
    ["T05", "5", "05", " 5 ", "tienda 5", "T-5", 5.0, "#5", "Tienda No. 5", "t5", "NOVAMERCADO QUETZALTENANGO"],
)
def test_tienda_en_otro_formato_se_repara(catalogo, prediccion, valor):
    prediccion["tienda_id"] = valor
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.tienda_id == 5
    assert _acciones(obs) == [("tienda_id", "reparar")]


@pytest.mark.parametrize(
    "valor", [99, "T99", "abc", "5-10", None, True, 5.5, [5], "Quetzaltenango", "Zona 5", "sucursal 5"]
)
def test_tienda_inexistente_o_ambigua_se_rechaza(catalogo, prediccion, valor):
    prediccion["tienda_id"] = valor
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


def test_numero_dentro_del_nombre_no_se_confunde_con_otra_tienda(catalogo, prediccion):
    """'NovaMercado Zona 10' es la tienda 1, no la 10."""
    prediccion["tienda_id"] = "NovaMercado Zona 10"
    assert limpiar_prediccion(prediccion, catalogo)[0].tienda_id == 1
    prediccion["tienda_id"] = "NovaMercado Express Zona 1"
    assert limpiar_prediccion(prediccion, catalogo)[0].tienda_id == 4
    prediccion["tienda_id"] = "Zona 10"
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


# ------------------------------------------------------------ E02 familia

@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("LÁCTEOS", "lacteos"),
        ("lacteos ", "lacteos"),
        ("Frutas y Verduras", "frutas_verduras"),
        ("frutas-verduras", "frutas_verduras"),
        ("Cuidado Personal", "cuidado_personal"),
        ("Snacks y dulces", "snacks"),
        ("BEBÉ", "bebe"),
        ("panadería", "panaderia"),
    ],
)
def test_familia_escrita_de_otra_forma_se_repara(catalogo, texto, esperado):
    assert resolver_familia(texto, catalogo) == (esperado, "reparar")


def test_familia_parecida_se_advierte(catalogo):
    assert resolver_familia("lacteo", catalogo) == ("lacteos", "advertir")
    assert resolver_familia("mascota", catalogo) == ("mascotas", "advertir")


@pytest.mark.parametrize("texto", ["electronica", "", None, 7, "xx"])
def test_familia_desconocida_no_se_resuelve(catalogo, texto):
    assert resolver_familia(texto, catalogo) == (None, None)


def test_familia_desconocida_se_omite_y_el_resto_se_predice(catalogo, prediccion):
    prediccion["familias"].append({"familia_id": "electronica", "en_promocion": 1})
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert "electronica" not in _promos(solicitud)
    assert ("familias[12].familia_id", "advertir") in _acciones(obs)


# ------------------------------------------------------------ E03 promoción

@pytest.mark.parametrize("valor, esperado", [("3", 3), (2.0, 2), (" 4 ", 4), ("1,000", 1000)])
def test_promocion_texto_o_decimal_entero_se_repara(catalogo, prediccion, valor, esperado):
    prediccion["familias"][0]["en_promocion"] = valor
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == esperado
    assert _acciones(obs) == [("familias[0].en_promocion", "reparar")]


@pytest.mark.parametrize("valor, esperado", [(None, 0), ("tres", 0), (-2, 0), (2.6, 3), (True, 0)])
def test_promocion_dudosa_se_advierte(catalogo, prediccion, valor, esperado):
    prediccion["familias"][0]["en_promocion"] = valor
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == esperado
    assert _acciones(obs) == [("familias[0].en_promocion", "advertir")]


def test_promocion_ausente_se_advierte(catalogo, prediccion):
    del prediccion["familias"][0]["en_promocion"]
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == 0
    assert Calidad.desde(obs).estado == "advertencia"


# ------------------------------------------------------------ E04 fecha

@pytest.mark.parametrize(
    "texto",
    ["2025-11-17T00:00:00", "2025-11-17 00:00:00", "2025-11-17T00:00:00Z", "17/11/2025",
     "2025/11/17", "17-11-2025", "20251117", "11/17/2025", "17.11.2025", " 2025-11-17 "],
)
def test_fecha_en_otro_formato_inequivoco_se_repara(catalogo, prediccion, texto):
    prediccion["fecha"] = texto
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.fecha == date(2025, 11, 17)
    assert _acciones(obs) == [("fecha", "reparar")]


@pytest.mark.parametrize("texto", ["05/11/2025", "11-05-2025", "1.2.2026"])
def test_fecha_ambigua_se_rechaza(catalogo, prediccion, texto):
    prediccion["fecha"] = texto
    with pytest.raises(Rechazo, match="ambigua"):
        limpiar_prediccion(prediccion, catalogo)


def test_fecha_con_dia_y_mes_iguales_no_es_ambigua(catalogo, prediccion):
    prediccion["fecha"] = "07/07/2026"
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.fecha == date(2026, 7, 7)
    assert _acciones(obs) == [("fecha", "reparar")]


@pytest.mark.parametrize("texto", ["2025-02-30", "mañana", "", None, 20251117, "31/31/2025", "2025-13-01"])
def test_fecha_ilegible_o_inexistente_se_rechaza(catalogo, prediccion, texto):
    prediccion["fecha"] = texto
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


def test_fecha_anterior_a_la_apertura_se_rechaza(catalogo, prediccion):
    prediccion["tienda_id"] = 10
    prediccion["fecha"] = "2025-03-14"
    with pytest.raises(Rechazo, match="apertura"):
        limpiar_prediccion(prediccion, catalogo)


def test_fecha_futura_lejana_se_acepta_sin_usar_el_reloj(catalogo, prediccion):
    prediccion["fecha"] = "2031-01-05"
    solicitud, _ = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.fecha == date(2031, 1, 5)


# ------------------------------------------------------------ E05 faltan familias

def test_faltan_familias_se_predicen_todas_con_advertencia(catalogo, prediccion):
    prediccion["familias"] = [f for f in prediccion["familias"] if f["familia_id"] not in ("bebe", "mascotas")]
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert len(solicitud.familias) == 12
    assert _promos(solicitud)["bebe"] == 0
    assert _acciones(obs) == [("familias", "advertir")]
    assert "bebe" in obs[0].detalle and "mascotas" in obs[0].detalle


def test_sin_familias_validas_se_rechaza(catalogo, prediccion):
    prediccion["familias"] = [{"familia_id": "electronica", "en_promocion": 0}]
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


@pytest.mark.parametrize("valor", [[], None, "abarrotes", {"familia_id": "abarrotes"}])
def test_lista_de_familias_invalida_se_rechaza(catalogo, prediccion, valor):
    prediccion["familias"] = valor
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


# ------------------------------------------------------------ E06 repetidas

def test_familia_repetida_con_valores_distintos_usa_la_ultima(catalogo, prediccion):
    prediccion["familias"].append({"familia_id": "abarrotes", "en_promocion": 3})
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == 3
    assert _acciones(obs) == [("familias[12]", "advertir")]


def test_familia_repetida_identica_se_repara(catalogo, prediccion):
    prediccion["familias"].append({"familia_id": "ABARROTES", "en_promocion": 0})
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert len(solicitud.familias) == 12
    assert Calidad.desde(obs).estado == "corregido"


# ------------------------------------------------------------ E07 campos

@pytest.mark.parametrize("clave", ["tienda", "Tienda_ID", "id_tienda", "store_id", "tiendaId"])
def test_nombre_de_campo_de_tienda_se_repara(catalogo, prediccion, clave):
    prediccion[clave] = prediccion.pop("tienda_id")
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.tienda_id == 5
    assert _acciones(obs) == [("tienda_id", "reparar")]


def test_nombres_de_campo_de_familia_se_reparan(catalogo, prediccion):
    prediccion["familias"][0] = {"familia": "abarrotes", "promocion": 2}
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == 2
    assert Calidad.desde(obs).estado == "corregido"


def test_campo_extra_desconocido_se_ignora_con_advertencia(catalogo, prediccion):
    prediccion["canal"] = "pos"
    _, obs = limpiar_prediccion(prediccion, catalogo)
    assert _acciones(obs) == [("canal", "advertir")]


def test_dos_campos_de_tienda_con_valores_distintos_se_rechaza(catalogo, prediccion):
    prediccion["tienda"] = 1
    with pytest.raises(Rechazo):
        limpiar_prediccion(prediccion, catalogo)


def test_dos_campos_de_tienda_con_el_mismo_valor_se_acepta(catalogo, prediccion):
    prediccion["tienda"] = 5
    solicitud, _ = limpiar_prediccion(prediccion, catalogo)
    assert solicitud.tienda_id == 5


@pytest.mark.parametrize("cuerpo", [None, [], "texto", 5])
def test_cuerpo_que_no_es_objeto_se_rechaza(catalogo, cuerpo):
    with pytest.raises(Rechazo):
        limpiar_prediccion(cuerpo, catalogo)


def test_falta_la_fecha_se_rechaza(catalogo, prediccion):
    del prediccion["fecha"]
    with pytest.raises(Rechazo, match="fecha"):
        limpiar_prediccion(prediccion, catalogo)


# ------------------------------------------------------------ E08 ventas negativas

def test_ventas_negativas_no_se_guardan(catalogo, observacion):
    observacion["ventas"][5]["ventas"] = -4
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    familia = observacion["ventas"][5]["familia_id"]
    assert familia not in {v.familia_id for v in solicitud.ventas}
    assert _acciones(obs) == [("ventas[5].ventas", "advertir")]


@pytest.mark.parametrize("valor", [None, "n/d", "", [1]])
def test_ventas_ilegibles_no_se_guardan(catalogo, observacion, valor):
    observacion["ventas"][0]["ventas"] = valor
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    assert len(solicitud.ventas) == 11
    assert _acciones(obs) == [("ventas[0].ventas", "advertir")]


# ------------------------------------------------------------ E10 números

@pytest.mark.parametrize(
    "texto, esperado",
    [("1,234", 1234), ("812,0", 812), ("1.234,5", 1234.5), ("1,234.5", 1234.5), ("12,5", 12.5),
     ("1 234", 1234), ("1,234,567", 1234567), ("1.234.567", 1234567), ("-4", -4), ("994", 994),
     (994, 994), (2.5, 2.5)],
)
def test_numeros_en_distintos_formatos(texto, esperado):
    assert a_numero(texto) == esperado


@pytest.mark.parametrize("texto", ["abc", "", "1,2,3", "1..2", None, True, float("nan"), "1e5x"])
def test_textos_que_no_son_numeros(texto):
    assert a_numero(texto) is None


def test_ventas_con_formato_se_reparan(catalogo, observacion):
    observacion["ventas"][0]["ventas"] = "1,292"
    observacion["ventas"][1]["ventas"] = "50,0"
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    ventas = {v.familia_id: v.ventas for v in solicitud.ventas}
    assert ventas[observacion["ventas"][0]["familia_id"]] == 1292
    assert ventas[observacion["ventas"][1]["familia_id"]] == 50
    assert Calidad.desde(obs).estado == "corregido"


@pytest.mark.parametrize("texto", ["1.234", " 1.234 ", "12.500"])
def test_ventas_con_punto_y_tres_decimales_son_ambiguas_y_no_se_guardan(catalogo, observacion, texto):
    observacion["ventas"][0]["ventas"] = texto
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    assert len(solicitud.ventas) == 11
    assert _acciones(obs) == [("ventas[0].ventas", "advertir")]
    assert "ambiguo" in obs[0].detalle


def test_ventas_con_punto_y_uno_o_dos_decimales_no_son_ambiguas(catalogo, observacion):
    observacion["ventas"][0]["ventas"] = "812.0"
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    assert len(solicitud.ventas) == 12
    assert _acciones(obs) == [("ventas[0].ventas", "reparar")]


def test_promocion_ambigua_se_asume_cero(catalogo, prediccion):
    prediccion["familias"][0]["en_promocion"] = "1.000"
    solicitud, obs = limpiar_prediccion(prediccion, catalogo)
    assert _promos(solicitud)["abarrotes"] == 0
    assert _acciones(obs) == [("familias[0].en_promocion", "advertir")]


def test_ventas_decimales_se_redondean_con_advertencia(catalogo, observacion):
    observacion["ventas"][0]["ventas"] = "12,5"
    _, obs = limpiar_observaciones(observacion, catalogo)
    assert _acciones(obs) == [("ventas[0].ventas", "advertir")]


def test_observacion_parcial_advierte_familias_faltantes(catalogo, observacion):
    observacion["ventas"] = observacion["ventas"][:3]
    solicitud, obs = limpiar_observaciones(observacion, catalogo)
    assert len(solicitud.ventas) == 3
    assert _acciones(obs) == [("ventas", "advertir")]


def test_observacion_con_tienda_inexistente_se_rechaza(catalogo, observacion):
    observacion["tienda_id"] = "T77"
    with pytest.raises(Rechazo):
        limpiar_observaciones(observacion, catalogo)


# ------------------------------------------------------------ estado de calidad

def test_estado_advertencia_tiene_prioridad_sobre_corregido(catalogo, prediccion):
    prediccion["tienda_id"] = "T05"                  # reparar
    prediccion["familias"][0]["en_promocion"] = None  # advertir
    _, obs = limpiar_prediccion(prediccion, catalogo)
    assert Calidad.desde(obs).estado == "advertencia"


def test_calidad_incoherente_no_se_puede_construir():
    with pytest.raises(ValueError):
        Calidad(estado="ok", observaciones=[{"campo": "x", "accion": "reparar", "detalle": "y"}])
