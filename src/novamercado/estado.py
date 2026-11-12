"""Modelo en memoria y estado de las dependencias.

- El servicio predice siempre con el modelo que tiene en memoria. Si MLflow se
  cae, sigue respondiendo con él.
- Un hilo revisa cada ``intervalo`` segundos la base de datos, MLflow y Airflow.
  Si el alias vigente apunta a otra versión, la descarga y la usa sin reiniciar.
- Cada modelo descargado se guarda en una carpeta local (un volumen de Docker).
  Si el servicio arranca con MLflow caído, usa esa copia.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from novamercado.modelo import Pronosticador

log = logging.getLogger("novamercado")


@dataclass
class Dependencias:
    base_datos: bool = False
    mlflow: bool = False
    airflow: bool = False
    revisado_en: float = field(default_factory=time.time)


class GestorModelo:
    def __init__(
        self,
        nombre: str,
        alias: str,
        consultar_version: Callable[[], str | None],
        descargar: Callable[[], tuple[Pronosticador, str]],
        dir_cache: str | Path | None = None,
    ):
        self.nombre, self.alias = nombre, alias
        self._consultar_version = consultar_version
        self._descargar = descargar
        self.dir_cache = Path(dir_cache) if dir_cache else None
        self.modelo: Pronosticador | None = None
        self.version: str | None = None
        self._candado = threading.Lock()

    @property
    def cargado(self) -> bool:
        return self.modelo is not None

    def actual(self) -> tuple[Pronosticador | None, str | None]:
        with self._candado:
            return self.modelo, self.version

    def _usar(self, modelo: Pronosticador, version: str) -> None:
        with self._candado:
            self.modelo, self.version = modelo, version

    def refrescar(self) -> bool:
        """Consulta MLflow y carga la versión vigente si cambió. Devuelve si MLflow respondió."""
        try:
            version = self._consultar_version()
            if version is not None and version != self.version:
                modelo, version = self._descargar()
                self._usar(modelo, version)
                self._guardar_cache(modelo, version)
                log.info("Modelo vigente cargado: versión %s", version)
            return True
        except Exception as e:  # MLflow caído o sin conexión
            log.warning("MLflow no disponible: %s", e)
            if not self.cargado:
                self.cargar_cache()
            return False

    def _guardar_cache(self, modelo: Pronosticador, version: str) -> None:
        if self.dir_cache is None:
            return
        try:
            destino = self.dir_cache / "vigente"
            modelo.guardar(destino)
            (destino / "version.txt").write_text(version)
        except OSError as e:
            log.warning("No se pudo guardar la copia local del modelo: %s", e)

    def cargar_cache(self) -> bool:
        if self.dir_cache is None or not (self.dir_cache / "vigente" / "version.txt").exists():
            return False
        try:
            origen = self.dir_cache / "vigente"
            self._usar(Pronosticador.cargar(origen), (origen / "version.txt").read_text().strip())
            log.info("Modelo cargado desde la copia local: versión %s", self.version)
            return True
        except Exception as e:
            log.warning("Copia local del modelo inválida: %s", e)
            return False


class Monitor:
    def __init__(self, gestor: GestorModelo, revisar_db: Callable[[], bool],
                 revisar_airflow: Callable[[], bool], intervalo: float = 15.0):
        self.gestor = gestor
        self._revisar_db, self._revisar_airflow = revisar_db, revisar_airflow
        self.intervalo = intervalo
        self.dependencias = Dependencias()
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None

    def revisar(self) -> Dependencias:
        self.dependencias = Dependencias(
            base_datos=self._seguro(self._revisar_db),
            mlflow=self.gestor.refrescar(),
            airflow=self._seguro(self._revisar_airflow),
        )
        return self.dependencias

    @staticmethod
    def _seguro(funcion: Callable[[], bool]) -> bool:
        try:
            return bool(funcion())
        except Exception:
            return False

    def iniciar(self) -> None:
        def ciclo():
            while not self._detener.is_set():
                self.revisar()
                self._detener.wait(self.intervalo)

        self._hilo = threading.Thread(target=ciclo, name="monitor", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._detener.set()

    def salud(self) -> tuple[int, dict]:
        if not self.gestor.cargado:
            return 503, {"estado": "degradado", "motivo": "todavía no hay un modelo cargado"}
        d = self.dependencias
        caidas = [nombre for nombre, ok in (("base de datos", d.base_datos), ("MLflow", d.mlflow),
                                            ("Airflow", d.airflow)) if not ok]
        if caidas:
            return 200, {
                "estado": "degradado",
                "motivo": f"no disponible: {', '.join(caidas)}; se responde con el modelo cargado "
                          f"(versión {self.gestor.version})",
            }
        return 200, {"estado": "ok", "version_modelo": self.gestor.version}
