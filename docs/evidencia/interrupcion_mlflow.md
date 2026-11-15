# Interrupción de MLflow

Generado con `scripts/probar_interrupcion_mlflow.sh` el 2026-11-14 10:56.

| Momento | Resultado |
|---|---|
| Antes | `{"estado":"ok","version_modelo":"2"}` |
| MLflow detenido (`docker compose stop mlflow`) | `/health` degradado en **21 s** (límite: 60 s) |
| Durante | `{"estado":"degradado","motivo":"no disponible: MLflow; se responde con el modelo cargado (versión 2)"}` |
| Pronóstico con MLflow detenido | HTTP **200**, `version_modelo` 2 |
| MLflow iniciado (`docker compose start mlflow`) | `/health` sin MLflow en el motivo en **14 s** (límite: 120 s) |
| Después | `{"estado":"ok","version_modelo":"2"}` |
