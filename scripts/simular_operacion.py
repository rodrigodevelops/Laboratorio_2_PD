"""Simula la operación diaria de las tiendas contra la API, como el programa de evaluación.

Cada día D del periodo:

1. Envía las ventas reales del día D−1 (``POST /v1/observaciones``).
2. Pide el pronóstico del día D para cada tienda (``POST /v1/prediccion``).
   Una parte de las solicitudes llega con defectos, incluidos algunos que no están
   en el catálogo.
3. Cada ``--reentrenar-cada`` días dispara un reentrenamiento y espera su resultado.

Las "ventas reales" se construyen con el histórico de la misma fecha del año
anterior (52 semanas antes); desde ``--cambio-desde`` se multiplican por el
factor indicado por familia, para simular un cambio en la demanda.

Al final escribe un reporte en Markdown con el costo de las sugerencias por
semana y versión del modelo, los reentrenamientos y ejemplos de respuestas.

Uso:
    python scripts/simular_operacion.py --desde 2026-03-01 --dias 28 \\
        --cambio-desde 2026-03-08 --cambio bebidas=1.5,snacks=1.5 --reentrenar-cada 7
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import pandas as pd


# ---------------------------------------------------------------- datos de la simulación

def cargar(dir_datos: Path):
    historico = pd.read_csv(dir_datos / "historico_ventas.csv", parse_dates=["fecha"])
    costos = pd.read_csv(dir_datos / "costos.csv").set_index("familia_id")
    tiendas = pd.read_csv(dir_datos / "tiendas.csv")
    return historico, costos, tiendas


class Realidad:
    """Ventas y promociones "reales" del periodo simulado."""

    def __init__(self, historico: pd.DataFrame, cambio_desde, factores: dict[str, float], semilla: int):
        self.h = historico.set_index(["fecha", "tienda_id", "familia_id"]).sort_index()
        self.fin = historico["fecha"].max()
        self.cambio_desde = pd.Timestamp(cambio_desde) if cambio_desde else None
        self.factores = factores
        self.rng = random.Random(semilla)
        self._cache: dict = {}

    def _base(self, fecha: pd.Timestamp, tienda: int, familia: str) -> tuple[float, int]:
        anterior = fecha - pd.Timedelta(days=364)
        if (anterior, tienda, familia) in self.h.index:
            fila = self.h.loc[(anterior, tienda, familia)]
            return float(fila["ventas"]), int(fila["en_promocion"])
        # Sin dato del año anterior (tienda nueva): media del mismo día de la semana al final del histórico.
        dias = [self.fin - pd.Timedelta(days=k) for k in range(28)]
        valores = [float(self.h.loc[(d, tienda, familia), "ventas"]) for d in dias
                   if d.dayofweek == fecha.dayofweek and (d, tienda, familia) in self.h.index]
        return (sum(valores) / len(valores) if valores else 0.0), 0

    def dia(self, fecha: pd.Timestamp, tienda: int, familia: str) -> tuple[float, int]:
        clave = (fecha, tienda, familia)
        if clave not in self._cache:
            ventas, promo = self._base(fecha, tienda, familia)
            if self.cambio_desde is not None and fecha >= self.cambio_desde:
                ventas *= self.factores.get(familia, 1.0)
            self._cache[clave] = (float(round(ventas)), promo)
        return self._cache[clave]


# ---------------------------------------------------------------- defectos

def _defectos_prediccion(cuerpo: dict, rng: random.Random) -> tuple[dict, str]:
    """Aplica un defecto al azar. Algunos están en el catálogo y otros no."""
    c = copy.deepcopy(cuerpo)
    opciones = [
        ("tienda con prefijo", lambda: c.update(tienda_id=f"T{c['tienda_id']:02d}")),
        ("tienda como texto con espacios", lambda: c.update(tienda_id=f" {c['tienda_id']} ")),
        ("familia en mayúsculas y con tildes", lambda: c["familias"][2].update(
            familia_id={"lacteos": "LÁCTEOS", "panaderia": "Panadería", "bebe": "BEBÉ"}.get(
                c["familias"][2]["familia_id"], c["familias"][2]["familia_id"].upper()))),
        ("promoción como texto", lambda: c["familias"][0].update(en_promocion=str(c["familias"][0]["en_promocion"]))),
        ("fecha con hora", lambda: c.update(fecha=c["fecha"] + "T00:00:00")),
        ("fecha en formato AAAA/MM/DD", lambda: c.update(fecha=c["fecha"].replace("-", "/"))),
        ("campo de tienda renombrado", lambda: c.update(tienda=c.pop("tienda_id"))),
        ("campo extra desconocido", lambda: c.update(canal="pos-v2")),
        ("faltan dos familias", lambda: c.update(familias=c["familias"][:-2])),
        ("familia repetida", lambda: c["familias"].append(dict(c["familias"][0], en_promocion=3))),
        ("promoción ausente", lambda: c["familias"][1].pop("en_promocion")),
        ("promoción decimal", lambda: c["familias"][3].update(en_promocion=float(c["familias"][3]["en_promocion"]))),
    ]
    nombre, aplicar = rng.choice(opciones)
    aplicar()
    return c, nombre


def _defectos_observacion(cuerpo: dict, rng: random.Random) -> tuple[dict, str]:
    c = copy.deepcopy(cuerpo)
    opciones = [
        ("ventas con separador de miles", lambda: [v.update(ventas=f"{int(v['ventas']):,}") for v in c["ventas"]]),
        ("ventas con coma decimal", lambda: c["ventas"][0].update(ventas=f"{int(c['ventas'][0]['ventas'])},0")),
        ("ventas negativas", lambda: c["ventas"][4].update(ventas=-3)),
        ("familia escrita distinto", lambda: c["ventas"][5].update(familia_id=c["ventas"][5]["familia_id"].upper())),
    ]
    nombre, aplicar = rng.choice(opciones)
    aplicar()
    return c, nombre


# ---------------------------------------------------------------- simulación

class Simulacion:
    def __init__(self, args):
        self.args = args
        self.http = httpx.Client(base_url=args.url, timeout=30)
        self.rng = random.Random(args.semilla)
        historico, costos, tiendas = cargar(Path(args.datos))
        factores = dict(par.split("=") for par in args.cambio.split(",")) if args.cambio else {}
        self.realidad = Realidad(historico, args.cambio_desde, {k: float(v) for k, v in factores.items()}, args.semilla)
        self.costos = costos
        self.tiendas = tiendas[["tienda_id", "fecha_apertura"]].assign(
            fecha_apertura=lambda t: pd.to_datetime(t["fecha_apertura"]))
        self.familias = sorted(costos.index)
        self.costo_filas = []  # (fecha, versión, costo, unidades)
        self.estados = Counter()
        self.defectos = Counter()
        self.reentrenamientos = []
        self.ejemplos = {}

    def _tiendas_abiertas(self, fecha):
        return [int(t) for t, a in self.tiendas.itertuples(index=False) if a <= fecha]

    def observar(self, fecha):
        for tienda in self._tiendas_abiertas(fecha):
            cuerpo = {"tienda_id": tienda, "fecha": str(fecha.date()), "ventas": [
                {"familia_id": f, "ventas": self.realidad.dia(fecha, tienda, f)[0]} for f in self.familias]}
            nombre = None
            if self.rng.random() < self.args.prob_defecto:
                cuerpo, nombre = _defectos_observacion(cuerpo, self.rng)
                self.defectos[f"observación: {nombre}"] += 1
            r = self.http.post("/v1/observaciones", json=cuerpo)
            self.estados[f"observaciones {r.status_code} {r.json().get('calidad', {}).get('estado', '')}".strip()] += 1
            if nombre and nombre not in self.ejemplos:
                self.ejemplos[f"observación: {nombre}"] = (cuerpo, r.status_code, r.json())
            if self.rng.random() < 0.05:  # reenvío idéntico
                r2 = self.http.post("/v1/observaciones", json=cuerpo)
                self.estados["observaciones reenviadas"] += 1
                self.ejemplos.setdefault("observación reenviada (idempotencia)", (cuerpo, r2.status_code, r2.json()))

    def pronosticar(self, fecha):
        for tienda in self._tiendas_abiertas(fecha):
            cuerpo = {"tienda_id": tienda, "fecha": str(fecha.date()), "familias": [
                {"familia_id": f, "en_promocion": self.realidad.dia(fecha, tienda, f)[1]} for f in self.familias]}
            nombre = None
            if self.rng.random() < self.args.prob_defecto:
                cuerpo, nombre = _defectos_prediccion(cuerpo, self.rng)
                self.defectos[f"pronóstico: {nombre}"] += 1
            r = self.http.post("/v1/prediccion", json=cuerpo)
            cuerpo_r = r.json()
            self.estados[f"prediccion {r.status_code} {cuerpo_r.get('calidad', {}).get('estado', '')}".strip()] += 1
            if nombre and nombre not in self.ejemplos:
                self.ejemplos[f"pronóstico: {nombre}"] = (cuerpo, r.status_code, cuerpo_r)
            if r.status_code != 200:
                continue
            self.ejemplos.setdefault("pronóstico válido", (cuerpo, r.status_code, cuerpo_r))
            for p in cuerpo_r["predicciones"]:
                real = self.realidad.dia(fecha, tienda, p["familia_id"])[0]
                cf, cs = self.costos.loc[p["familia_id"], ["costo_faltante", "costo_sobrante"]]
                sug = p["cantidad_sugerida"]
                costo = cf * max(real - sug, 0) + cs * max(sug - real, 0)
                self.costo_filas.append((fecha, cuerpo_r["version_modelo"], costo, real, p["venta_esperada"]))

    def reentrenar(self, fecha):
        r = self.http.post("/admin/reentrenar")
        if r.status_code != 202:
            self.reentrenamientos.append({"fecha": str(fecha.date()), "estado": f"HTTP {r.status_code}", **r.json()})
            return
        id_ = r.json()["id"]
        inicio = time.time()
        while time.time() - inicio < 660:
            estado = self.http.get(f"/admin/reentrenar/{id_}").json()
            if estado["estado"] != "en_curso":
                break
            time.sleep(5)
        estado["duracion_s"] = round(time.time() - inicio)
        estado["id"], estado["fecha"] = id_, str(fecha.date())
        self.reentrenamientos.append(estado)
        print(f"  reentrenamiento {id_}: {json.dumps(estado, ensure_ascii=False)}")
        # La API recarga el modelo en su siguiente revisión (máximo 15 s).
        time.sleep(20 if estado.get("promovido") else 0)

    def ejemplos_catalogo(self):
        """Envía los ejemplos publicados y casos rechazados, para la evidencia."""
        carpeta = Path(self.args.datos) / "ejemplos"
        for ruta in sorted(carpeta.glob("**/*.json")):
            cuerpo = json.loads(ruta.read_text())
            endpoint = "/v1/observaciones" if "ventas" in cuerpo else "/v1/prediccion"
            r = self.http.post(endpoint, json=cuerpo)
            self.ejemplos[f"catálogo: {ruta.stem}"] = (cuerpo, r.status_code, r.json())
        fecha = str(pd.Timestamp(self.args.desde).date())
        for nombre, cuerpo in [
            ("rechazo: tienda inexistente", {"tienda_id": 99, "fecha": fecha, "familias": [{"familia_id": "abarrotes", "en_promocion": 0}]}),
            ("rechazo: fecha ambigua", {"tienda_id": 1, "fecha": "05/03/2026", "familias": [{"familia_id": "abarrotes", "en_promocion": 0}]}),
            ("rechazo: número en el nombre de otra tienda", {"tienda_id": "Zona 10", "fecha": fecha, "familias": [{"familia_id": "abarrotes", "en_promocion": 0}]}),
            ("rechazo: sin familias válidas", {"tienda_id": 1, "fecha": fecha, "familias": [{"familia_id": "electronica", "en_promocion": 1}]}),
        ]:
            r = self.http.post("/v1/prediccion", json=cuerpo)
            self.ejemplos[nombre] = (cuerpo, r.status_code, r.json())

    def esperar_listo(self, limite_s: int = 600):
        """No empieza hasta que /health diga ok: con el producto a medio arrancar, los
        pronósticos responden 503 (sin modelo) y los reentrenamientos, 503 (sin Airflow)."""
        inicio = time.time()
        while time.time() - inicio < limite_s:
            try:
                r = self.http.get("/health")
                if r.status_code == 200 and r.json().get("estado") == "ok":
                    print(f"Producto listo tras {time.time() - inicio:.0f} s de espera")
                    return
                print(f"Esperando al producto: {r.status_code} {r.json()}")
            except httpx.HTTPError as e:
                print(f"Esperando al producto: {e.__class__.__name__}")
            time.sleep(10)
        sys.exit("El producto no llegó a /health ok en 10 minutos")

    def correr(self):
        desde = pd.Timestamp(self.args.desde)
        self.esperar_listo()
        print(f"Modelo vigente al inicio: {self.http.get('/modelo').json()}")
        self.ejemplos_catalogo()
        for i in range(self.args.dias):
            fecha = desde + pd.Timedelta(days=i)
            if i > 0:
                self.observar(fecha - pd.Timedelta(days=1))
            if self.args.reentrenar_cada and i > 0 and i % self.args.reentrenar_cada == 0:
                self.reentrenar(fecha)
            self.pronosticar(fecha)
            print(f"{fecha.date()} listo")
        self.observar(desde + pd.Timedelta(days=self.args.dias - 1))
        if self.args.reentrenar_cada:
            self.reentrenar(desde + pd.Timedelta(days=self.args.dias))
        return self.reporte()

    # ------------------------------------------------------------ reporte

    def reporte(self) -> str:
        df = pd.DataFrame(self.costo_filas, columns=["fecha", "version", "costo", "real", "esperada"])
        df["fecha"] = pd.to_datetime(df["fecha"])
        if df.empty:
            print("ATENCIÓN: ningún pronóstico respondió 200. Respuestas recibidas:")
            for k, v in sorted(self.estados.items()):
                print(f"  {k}: {v}")
        df["semana"] = df["fecha"].dt.to_period("W-SUN").dt.start_time.dt.date
        semanas = df.groupby(["semana", "version"]).agg(
            costo=("costo", "sum"), ventas=("real", "sum"),
            error=("esperada", lambda s: (s - df.loc[s.index, "real"]).abs().sum())).reset_index()
        semanas["wape"] = semanas["error"] / semanas["ventas"]
        semanas["costo_por_unidad"] = semanas["costo"] / semanas["ventas"]

        a = self.args
        lineas = [
            "# Prueba de operación simulada",
            "",
            f"Generado con `scripts/simular_operacion.py`: {a.dias} días desde {a.desde}, "
            f"{a.prob_defecto:.0%} de solicitudes con defectos, reentrenamiento cada {a.reentrenar_cada} días"
            + (f", cambio de demanda desde {a.cambio_desde} ({a.cambio})." if a.cambio else "."),
            "",
            "## Costo de las sugerencias por semana",
            "",
            "| Semana | Versión | Costo | Ventas reales | Costo por unidad vendida | WAPE |",
            "|---|---|---|---|---|---|",
            *[f"| {r.semana} | {r.version} | {r.costo:,.0f} | {r.ventas:,.0f} | {r.costo_por_unidad:.3f} | {r.wape:.3f} |"
              for r in semanas.itertuples()],
            "",
            f"**Total:** costo {df['costo'].sum():,.0f} sobre {df['real'].sum():,.0f} unidades vendidas."
            if len(df) else "**Ningún pronóstico respondió 200.** Ver las respuestas por estado.",
            "",
            "## Reentrenamientos",
            "",
            "| Fecha simulada | Estado | Promovido | Versión | Duración | Motivo |",
            "|---|---|---|---|---|---|",
            *[f"| {r.get('fecha')} | {r.get('estado')} | {r.get('promovido')} | {r.get('version')} | "
              f"{r.get('duracion_s', '')} s | {r.get('motivo') or r.get('detail', '')} |" for r in self.reentrenamientos],
            "",
            "## Respuestas por estado",
            "",
            *[f"- {k}: {v}" for k, v in sorted(self.estados.items())],
            "",
            "## Defectos enviados",
            "",
            *[f"- {k}: {v}" for k, v in sorted(self.defectos.items())],
            "",
            "## Ejemplos de solicitudes y respuestas",
            "",
        ]
        for nombre, (cuerpo, codigo, respuesta) in self.ejemplos.items():
            if isinstance(respuesta, dict) and "predicciones" in respuesta:
                respuesta = dict(respuesta, predicciones=respuesta["predicciones"][:3] + ["…"])
            if isinstance(cuerpo, dict) and isinstance(cuerpo.get("familias"), list) and len(cuerpo["familias"]) > 4:
                cuerpo = dict(cuerpo, familias=cuerpo["familias"][:3] + ["…"])
            if isinstance(cuerpo, dict) and isinstance(cuerpo.get("ventas"), list) and len(cuerpo["ventas"]) > 4:
                cuerpo = dict(cuerpo, ventas=cuerpo["ventas"][:3] + ["…"])
            lineas += [f"### {nombre}", "", "Solicitud:", "", "```json",
                       json.dumps(cuerpo, ensure_ascii=False, indent=2), "```", "",
                       f"Respuesta (HTTP {codigo}):", "", "```json",
                       json.dumps(respuesta, ensure_ascii=False, indent=2), "```", ""]
        return "\n".join(lineas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--datos", default="datos/publicados")
    p.add_argument("--desde", default="2026-03-01")
    p.add_argument("--dias", type=int, default=28)
    p.add_argument("--cambio-desde", default=None)
    p.add_argument("--cambio", default="", help="factores por familia, p. ej. bebidas=1.5,snacks=1.5")
    p.add_argument("--reentrenar-cada", type=int, default=7)
    p.add_argument("--prob-defecto", type=float, default=0.25)
    p.add_argument("--semilla", type=int, default=7)
    p.add_argument("--salida", default="docs/evidencia/operacion.md")
    a = p.parse_args(argv)
    texto = Simulacion(a).correr()
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.salida).write_text(texto, encoding="utf-8")
    print(f"Reporte escrito en {a.salida}")


if __name__ == "__main__":
    sys.exit(main())
