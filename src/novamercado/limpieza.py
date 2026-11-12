"""Limpieza de las solicitudes que envían las tiendas.

Política (ver DECISIONES.md):

- **Reparar**: hay una sola interpretación posible y no cambia el significado.
- **Advertir**: se responde, pero suponiendo algo; se informa qué.
- **Rechazar** (``Rechazo``, HTTP 422): no se puede saber qué se pide, porque la
  tienda o la fecha no se pueden determinar.

Los datos que identifican la solicitud (tienda y fecha) solo se reparan o se
rechazan. Los datos de cada familia se reparan o se advierten: un problema en una
familia nunca invalida toda la solicitud.

Las reglas son por tipo de campo, no por ejemplo del catálogo, para cubrir
problemas que no se han visto. No se usa el reloj del sistema: las fechas son
simuladas.
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from novamercado.catalogos import Catalogo
from novamercado.esquemas import (
    ObservacionCalidad,
    SolicitudObservaciones,
    SolicitudPrediccion,
)


class Rechazo(Exception):
    """La solicitud no se puede atender. Se responde 422 con ``detail``."""

    def __init__(self, detalle: str):
        super().__init__(detalle)
        self.detalle = detalle


class _Registro:
    def __init__(self) -> None:
        self.items: list[ObservacionCalidad] = []

    def reparar(self, campo: str, detalle: str) -> None:
        self.items.append(ObservacionCalidad(campo=campo, accion="reparar", detalle=detalle))

    def advertir(self, campo: str, detalle: str) -> None:
        self.items.append(ObservacionCalidad(campo=campo, accion="advertir", detalle=detalle))


# ---------------------------------------------------------------- texto

def normalizar(texto: Any) -> str:
    """Minúsculas, sin tildes, y cualquier separador convertido en ``_``."""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _compacto(texto: Any) -> str:
    return normalizar(texto).replace("_", "")


# ---------------------------------------------------------------- nombres de campo

SINONIMOS_RAIZ_PREDICCION = {
    "tienda_id": ["tienda", "id_tienda", "store_id", "store", "tienda_no", "no_tienda", "codigo_tienda"],
    "fecha": ["date", "dia", "fecha_pronostico", "fecha_prediccion"],
    "familias": ["familia", "families", "productos", "detalle", "items"],
}
SINONIMOS_RAIZ_OBSERVACION = {
    "tienda_id": SINONIMOS_RAIZ_PREDICCION["tienda_id"],
    "fecha": ["date", "dia", "fecha_venta", "fecha_observacion"],
    "ventas": ["venta", "sales", "observaciones", "detalle", "items"],
}
SINONIMOS_FAMILIA = {
    "familia_id": ["familia", "id_familia", "family", "family_id", "categoria"],
    "en_promocion": ["promocion", "promo", "en_promo", "promociones", "productos_en_promocion", "onpromotion"],
}
SINONIMOS_VENTA = {
    "familia_id": SINONIMOS_FAMILIA["familia_id"],
    "ventas": ["venta", "sales", "unidades", "cantidad", "valor"],
}


def _mapear_claves(
    datos: dict, sinonimos: dict[str, list[str]], prefijo: str, reg: _Registro, identidad: bool
) -> dict:
    """Renombra claves al contrato. Las claves desconocidas se ignoran con advertencia.

    Si dos claves distintas apuntan al mismo campo con valores diferentes, se
    rechaza (``identidad=True``) o se advierte y se usa el nombre del contrato.
    """
    tabla = {}
    for canonico, extras in sinonimos.items():
        for alias in [canonico, *extras]:
            tabla[_compacto(alias)] = canonico

    salida: dict[str, Any] = {}
    origen: dict[str, str] = {}
    for clave, valor in datos.items():
        canonico = tabla.get(_compacto(clave))
        if canonico is None:
            reg.advertir(f"{prefijo}{clave}", f"campo '{clave}' no pertenece al contrato; se ignoró")
            continue
        if canonico in salida:
            if salida[canonico] == valor:
                continue
            if identidad:
                raise Rechazo(
                    f"'{origen[canonico]}' y '{clave}' indican valores distintos para '{canonico}'"
                )
            otra = origen[canonico]
            if clave == canonico:  # se prefiere el nombre exacto del contrato
                salida[canonico], origen[canonico] = valor, clave
            reg.advertir(
                f"{prefijo}{canonico}",
                f"'{otra}' y '{clave}' indican valores distintos; se usó '{origen[canonico]}'",
            )
            continue
        salida[canonico], origen[canonico] = valor, clave
        if clave != canonico:
            reg.reparar(f"{prefijo}{canonico}", f"campo '{clave}' se interpretó como '{canonico}'")
    return salida


# ---------------------------------------------------------------- números

_MILES_COMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_MILES_PUNTO = re.compile(r"^\d{1,3}(\.\d{3}){2,}$")
_NUMERO = re.compile(r"^[+-]?\d+(\.\d+)?$")


def a_numero(valor: Any) -> float | None:
    """Convierte números escritos de distintas formas. ``None`` si no es un número.

    - Coma seguida de grupos de 3 dígitos: separador de miles (``"1,234"``).
    - Una coma seguida de 1 o 2 dígitos: coma decimal (``"812,0"``).
    - Punto y coma juntos: el último que aparece es el separador decimal.
    """
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) else None
    if not isinstance(valor, str):
        return None
    s = valor.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    signo = ""
    if s[0] in "+-":
        signo, s = s[0], s[1:]
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s:
        s = s.replace(",", "") if _MILES_COMA.match(s) else s.replace(",", ".", 1) if s.count(",") == 1 else s
    elif _MILES_PUNTO.match(s):
        s = s.replace(".", "")
    s = signo + s
    return float(s) if _NUMERO.match(s) else None


_PUNTO_TRES = re.compile(r"^[+-]?\d{1,3}\.\d{3}$")


def es_ambiguo(valor: Any) -> bool:
    """``"1.234"``: con la convención local es 1.234; como unidades enteras, 1234.

    Las dos lecturas razonables no coinciden, así que no se elige ninguna. Con
    coma (``"1,234"``) sí coinciden (miles y entero), por eso no es ambiguo.
    """
    return isinstance(valor, str) and bool(_PUNTO_TRES.match(valor.strip()))


def _describir(valor: Any) -> str:
    return f"'{valor}'" if isinstance(valor, str) else repr(valor)


# ---------------------------------------------------------------- tienda

# Un número con, a lo sumo, un prefijo corto: "5", "05", "T05", "T-5", "#5",
# "tienda 5", "Tienda No. 5". Un número dentro de otro texto no basta: en
# "NovaMercado Zona 10" el 10 es parte del nombre de la tienda 1.
_TIENDA_TEXTO = re.compile(r"^(?:(?:tienda|store|tda|t|no|nro|num|numero|id)_?)*0*(\d+)$")


def _tienda_desde_texto(valor: str, catalogo: Catalogo) -> int | None:
    m = _TIENDA_TEXTO.match(normalizar(valor))
    if m:
        return int(m[1])
    por_nombre = [t.tienda_id for t in catalogo.tiendas.values() if _compacto(t.nombre) == _compacto(valor)]
    return por_nombre[0] if len(por_nombre) == 1 else None


def limpiar_tienda(valor: Any, catalogo: Catalogo, reg: _Registro) -> int:
    if isinstance(valor, bool):
        raise Rechazo(f"tienda_id {_describir(valor)} no es un identificador de tienda")
    if isinstance(valor, int):
        tienda = valor
    elif isinstance(valor, float) and valor.is_integer():
        tienda = int(valor)
        reg.reparar("tienda_id", f"{valor!r} se interpretó como {tienda}")
    elif isinstance(valor, str):
        tienda = _tienda_desde_texto(valor, catalogo)
        if tienda is None:
            raise Rechazo(f"no se pudo determinar la tienda a partir de {_describir(valor)}")
        reg.reparar("tienda_id", f"{_describir(valor)} se interpretó como {tienda}")
    elif valor is None:
        raise Rechazo("falta tienda_id")
    else:
        raise Rechazo(f"tienda_id {_describir(valor)} no es un identificador de tienda")
    if tienda not in catalogo.tiendas:
        raise Rechazo(f"la tienda {tienda} no existe")
    return tienda


# ---------------------------------------------------------------- fecha

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_HORA = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[T ][\d:.]+(Z|[+-]\d{2}:?\d{2})?$")
_ANIO_PRIMERO = re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$")
_ANIO_ULTIMO = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_COMPACTA = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def _crear(anio: int, mes: int, dia: int, original: str) -> date:
    try:
        return date(anio, mes, dia)
    except ValueError:
        raise Rechazo(f"la fecha '{original}' no existe") from None


def limpiar_fecha(valor: Any, apertura: date, reg: _Registro) -> date:
    if valor is None:
        raise Rechazo("falta la fecha")
    if not isinstance(valor, str):
        raise Rechazo(f"la fecha {_describir(valor)} no es texto en formato AAAA-MM-DD")
    s = valor.strip()
    m = _ISO.match(s)
    if m:
        f = _crear(int(m[1]), int(m[2]), int(m[3]), valor)
        if s != valor:
            reg.reparar("fecha", f"'{valor}' se interpretó como '{f.isoformat()}'")
    elif m := _ISO_HORA.match(s) or _ANIO_PRIMERO.match(s) or _COMPACTA.match(s):
        f = _crear(int(m[1]), int(m[2]), int(m[3]), valor)
        reg.reparar("fecha", f"'{valor}' se interpretó como '{f.isoformat()}'")
    elif m := _ANIO_ULTIMO.match(s):
        a, b, anio = int(m[1]), int(m[2]), int(m[3])
        if a > 12 and b <= 12:
            f = _crear(anio, b, a, valor)
            reg.reparar("fecha", f"'{valor}' se interpretó como '{f.isoformat()}' (día/mes/año)")
        elif b > 12 and a <= 12:
            f = _crear(anio, a, b, valor)
            reg.reparar("fecha", f"'{valor}' se interpretó como '{f.isoformat()}' (mes/día/año)")
        elif a == b:
            f = _crear(anio, a, b, valor)
            reg.reparar("fecha", f"'{valor}' se interpretó como '{f.isoformat()}'")
        elif a <= 12 and b <= 12:
            raise Rechazo(
                f"la fecha '{valor}' es ambigua: puede ser día/mes o mes/día; se espera AAAA-MM-DD"
            )
        else:
            raise Rechazo(f"la fecha '{valor}' no existe")
    else:
        raise Rechazo(f"no se pudo interpretar la fecha '{valor}'; se espera AAAA-MM-DD")
    if f < apertura:
        raise Rechazo(f"la fecha {f.isoformat()} es anterior a la apertura de la tienda ({apertura.isoformat()})")
    return f


# ---------------------------------------------------------------- familia

def _indice_familias(catalogo: Catalogo) -> dict[str, str]:
    indice = {}
    for fid, nombre in catalogo.familias.items():
        for forma in (fid, nombre):
            indice[_compacto(forma)] = fid
            # "Frutas y verduras" -> "frutasverduras", "Snacks y dulces" -> "snacksdulces"
            indice[_compacto(re.sub(r"\b(y|e|de|del|la|el)\b", " ", normalizar(forma).replace("_", " ")))] = fid
    return indice


def resolver_familia(valor: Any, catalogo: Catalogo) -> tuple[str | None, str | None]:
    """Devuelve (familia_id, accion). accion es None, 'reparar' o 'advertir'."""
    if valor is None or isinstance(valor, (bool, dict, list)):
        return None, None
    texto = str(valor)
    if texto in catalogo.familias:
        return texto, None
    indice = _indice_familias(catalogo)
    clave = _compacto(texto)
    if clave in indice:
        return indice[clave], "reparar"
    parecidas = difflib.get_close_matches(clave, list(indice), n=2, cutoff=0.85)
    candidatas = {indice[p] for p in parecidas}
    if len(candidatas) == 1:
        return candidatas.pop(), "advertir"
    return None, None


# ---------------------------------------------------------------- promoción y ventas

def limpiar_promocion(valor: Any, campo: str, reg: _Registro) -> int:
    if es_ambiguo(valor):
        reg.advertir(campo, f"{_describir(valor)} es ambiguo (¿{valor} o {valor.replace('.', '')}?); se asumió 0 productos en promoción")
        return 0
    numero = a_numero(valor)
    if numero is None:
        detalle = "no se informó" if valor is None else f"{_describir(valor)} no es un número"
        reg.advertir(campo, f"{detalle}; se asumió 0 productos en promoción")
        return 0
    if numero < 0:
        reg.advertir(campo, f"{_describir(valor)} es negativo; se asumió 0 productos en promoción")
        return 0
    if not numero.is_integer():
        entero = round(numero)
        reg.advertir(campo, f"{_describir(valor)} no es entero; se redondeó a {entero}")
        return entero
    if not isinstance(valor, int) or isinstance(valor, bool):
        reg.reparar(campo, f"{_describir(valor)} se interpretó como {int(numero)}")
    return int(numero)


# ---------------------------------------------------------------- solicitudes

def _como_dict(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise Rechazo("el cuerpo de la solicitud debe ser un objeto JSON")
    return payload


def _lista(valor: Any, nombre: str) -> list:
    if valor is None:
        raise Rechazo(f"falta la lista '{nombre}'")
    if not isinstance(valor, list):
        raise Rechazo(f"'{nombre}' debe ser una lista")
    return valor


def _identidad(datos: dict, catalogo: Catalogo, reg: _Registro) -> tuple[int, date]:
    tienda = limpiar_tienda(datos.get("tienda_id"), catalogo, reg)
    fecha = limpiar_fecha(datos.get("fecha"), catalogo.tiendas[tienda].fecha_apertura, reg)
    return tienda, fecha


def limpiar_prediccion(
    payload: Any, catalogo: Catalogo
) -> tuple[SolicitudPrediccion, list[ObservacionCalidad]]:
    reg = _Registro()
    datos = _mapear_claves(_como_dict(payload), SINONIMOS_RAIZ_PREDICCION, "", reg, identidad=True)
    tienda, fecha = _identidad(datos, catalogo, reg)
    entrada = _lista(datos.get("familias"), "familias")

    elegidas: dict[str, tuple[int, int]] = {}  # familia_id -> (promoción, posición)
    for i, item in enumerate(entrada):
        campo = f"familias[{i}]"
        if not isinstance(item, dict):
            reg.advertir(campo, f"{_describir(item)} no es un objeto; se ignoró")
            continue
        item = _mapear_claves(item, SINONIMOS_FAMILIA, f"{campo}.", reg, identidad=False)
        original = item.get("familia_id")
        fid, accion = resolver_familia(original, catalogo)
        if fid is None:
            reg.advertir(f"{campo}.familia_id", f"familia {_describir(original)} desconocida; se omitió")
            continue
        if accion == "reparar":
            reg.reparar(f"{campo}.familia_id", f"{_describir(original)} se interpretó como '{fid}'")
        elif accion == "advertir":
            reg.advertir(f"{campo}.familia_id", f"{_describir(original)} se asumió como '{fid}' por parecido")
        promo = limpiar_promocion(item.get("en_promocion"), f"{campo}.en_promocion", reg)
        if fid in elegidas:
            anterior, pos = elegidas[fid]
            if anterior == promo:
                reg.reparar(campo, f"'{fid}' repetida con los mismos valores; se tomó una sola vez")
            else:
                reg.advertir(
                    campo,
                    f"'{fid}' repetida con valores distintos (familias[{pos}]: {anterior}, familias[{i}]: {promo}); "
                    "se usó la última aparición",
                )
        elegidas[fid] = (promo, i)

    if not elegidas:
        raise Rechazo("la solicitud no contiene ninguna familia de producto válida")

    faltantes = [f for f in catalogo.ids_familias if f not in elegidas]
    if faltantes:
        reg.advertir(
            "familias",
            f"no se recibieron {', '.join(faltantes)}; se pronosticaron asumiendo 0 productos en promoción",
        )
    familias = [
        {"familia_id": f, "en_promocion": elegidas[f][0] if f in elegidas else 0}
        for f in catalogo.ids_familias
    ]
    solicitud = SolicitudPrediccion.model_validate(
        {"tienda_id": tienda, "fecha": fecha, "familias": familias}
    )
    return solicitud, reg.items


def limpiar_observaciones(
    payload: Any, catalogo: Catalogo
) -> tuple[SolicitudObservaciones, list[ObservacionCalidad]]:
    reg = _Registro()
    datos = _mapear_claves(_como_dict(payload), SINONIMOS_RAIZ_OBSERVACION, "", reg, identidad=True)
    tienda, fecha = _identidad(datos, catalogo, reg)
    entrada = _lista(datos.get("ventas"), "ventas")

    elegidas: dict[str, tuple[float, int]] = {}
    recibidas: set[str] = set()
    for i, item in enumerate(entrada):
        campo = f"ventas[{i}]"
        if not isinstance(item, dict):
            reg.advertir(campo, f"{_describir(item)} no es un objeto; no se guardó")
            continue
        item = _mapear_claves(item, SINONIMOS_VENTA, f"{campo}.", reg, identidad=False)
        original = item.get("familia_id")
        fid, accion = resolver_familia(original, catalogo)
        if fid is None:
            reg.advertir(f"{campo}.familia_id", f"familia {_describir(original)} desconocida; no se guardó")
            continue
        if accion == "reparar":
            reg.reparar(f"{campo}.familia_id", f"{_describir(original)} se interpretó como '{fid}'")
        elif accion == "advertir":
            reg.advertir(f"{campo}.familia_id", f"{_describir(original)} se asumió como '{fid}' por parecido")
        recibidas.add(fid)

        valor = item.get("ventas")
        if es_ambiguo(valor):
            reg.advertir(
                f"{campo}.ventas",
                f"{_describir(valor)} es ambiguo (¿{valor} o {valor.strip().replace('.', '')} unidades?); no se guardó",
            )
            continue
        numero = a_numero(valor)
        if numero is None:
            detalle = "no se informó" if valor is None else f"{_describir(valor)} no es un número"
            reg.advertir(f"{campo}.ventas", f"{detalle}; no se guardó")
            continue
        if numero < 0:
            reg.advertir(
                f"{campo}.ventas",
                f"{_describir(valor)} es negativo (posible devolución); se desconoce la venta real y no se guardó",
            )
            continue
        if not numero.is_integer():
            entero = float(round(numero))
            reg.advertir(f"{campo}.ventas", f"{_describir(valor)} no es entero; se redondeó a {entero:.0f}")
            numero = entero
        elif not isinstance(valor, int) or isinstance(valor, bool):
            reg.reparar(f"{campo}.ventas", f"{_describir(valor)} se interpretó como {numero:.0f}")

        if fid in elegidas:
            anterior, pos = elegidas[fid]
            if anterior == numero:
                reg.reparar(campo, f"'{fid}' repetida con el mismo valor; se tomó una sola vez")
            else:
                reg.advertir(
                    campo,
                    f"'{fid}' repetida con valores distintos (ventas[{pos}]: {anterior:.0f}, "
                    f"ventas[{i}]: {numero:.0f}); se usó la última aparición",
                )
        elegidas[fid] = (numero, i)

    faltantes = [f for f in catalogo.ids_familias if f not in recibidas]
    if recibidas and faltantes:
        reg.advertir("ventas", f"no se recibieron ventas de {', '.join(faltantes)}")

    solicitud = SolicitudObservaciones.model_validate(
        {
            "tienda_id": tienda,
            "fecha": fecha,
            "ventas": [{"familia_id": f, "ventas": v} for f, (v, _) in sorted(elegidas.items())],
        }
    )
    return solicitud, reg.items
