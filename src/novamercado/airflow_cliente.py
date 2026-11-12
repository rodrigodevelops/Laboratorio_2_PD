"""Cliente mínimo de la API REST de Airflow 3 para disparar y consultar el DAG."""

from __future__ import annotations

import os
import time

import httpx


class AirflowNoDisponible(Exception):
    pass


class ClienteAirflow:
    def __init__(self, url: str, usuario: str, clave: str, dag_id: str, timeout: float = 5.0):
        self.url = url.rstrip("/")
        self.usuario, self.clave, self.dag_id = usuario, clave, dag_id
        self.timeout = timeout
        self._token: str | None = None
        self._token_hasta = 0.0

    @classmethod
    def desde_entorno(cls) -> "ClienteAirflow | None":
        url = os.environ.get("AIRFLOW_URL")
        if not url:
            return None
        return cls(
            url,
            os.environ.get("AIRFLOW_USUARIO", "airflow"),
            os.environ.get("AIRFLOW_CLAVE", "airflow"),
            os.environ.get("AIRFLOW_DAG_REENTRENAMIENTO", "reentrenamiento"),
        )

    def _encabezados(self) -> dict:
        if self._token is None or time.time() > self._token_hasta:
            r = httpx.post(f"{self.url}/auth/token", json={"username": self.usuario, "password": self.clave},
                           timeout=self.timeout)
            r.raise_for_status()
            self._token = r.json()["access_token"]
            self._token_hasta = time.time() + 600
        return {"Authorization": f"Bearer {self._token}"}

    def _pedir(self, metodo: str, ruta: str, **kwargs) -> httpx.Response:
        try:
            r = httpx.request(metodo, f"{self.url}{ruta}", headers=self._encabezados(), timeout=self.timeout, **kwargs)
            if r.status_code == 401:  # token vencido
                self._token = None
                r = httpx.request(metodo, f"{self.url}{ruta}", headers=self._encabezados(), timeout=self.timeout, **kwargs)
            return r
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise AirflowNoDisponible(str(e)) from e

    def disponible(self) -> bool:
        try:
            r = httpx.get(f"{self.url}/api/v2/monitor/health", timeout=self.timeout)
            return r.status_code == 200 and r.json().get("scheduler", {}).get("status") == "healthy"
        except (httpx.HTTPError, ValueError):
            return False

    def disparar(self, run_id: str) -> None:
        r = self._pedir("POST", f"/api/v2/dags/{self.dag_id}/dagRuns",
                        json={"dag_run_id": run_id, "logical_date": None})
        if r.status_code not in (200, 201):
            raise AirflowNoDisponible(f"Airflow respondió {r.status_code}: {r.text[:300]}")

    def estado(self, run_id: str) -> str | None:
        """queued, running, success, failed; ``None`` si no existe."""
        r = self._pedir("GET", f"/api/v2/dags/{self.dag_id}/dagRuns/{run_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise AirflowNoDisponible(f"Airflow respondió {r.status_code}")
        return r.json().get("state")
