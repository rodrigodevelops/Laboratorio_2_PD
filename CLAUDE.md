# Reglas del proyecto para el agente de programación

Servicio de pronóstico diario de ventas para NovaMercado: FastAPI, PostgreSQL,
MLflow y Airflow 3, todo con Docker Compose. Leer `README.md` y `DECISIONES.md`
antes de proponer cambios.

## Reglas no negociables

1. **El contrato del Anexo no se rompe.** No se omiten ni renombran campos de las
   respuestas. `version_modelo` es texto; `cantidad_sugerida`, entero no negativo.
   Los rechazos responden 422 con `detail`. Cualquier cambio de respuesta debe
   pasar por los modelos de `esquemas.py`.
2. **La limpieza vive en `limpieza.py`, no en los endpoints.** Las reglas son por
   tipo de campo, no por ejemplo del catálogo. La tienda y la fecha solo se
   reparan o se rechazan; nunca se suponen. Un problema en una familia nunca
   invalida toda la solicitud. Toda regla nueva va con su prueba y con su fila en
   la sección 1 de `DECISIONES.md`.
3. **Sin información del futuro.** Al predecir el día D solo se usan ventas hasta
   D−1, la promoción que trae la solicitud y el calendario. Si se agrega una
   variable, ampliar `test_features_no_usan_el_futuro`.
4. **No usar el reloj del sistema** para validar fechas: son simuladas.
5. **El vigente solo cambia moviendo el alias** en `registro.registrar`, y solo si
   el candidato supera el criterio de `reentrenamiento.py`. El vigente se evalúa
   con las predicciones que realmente entregó; nunca con días que ya vio.
6. **La API siempre responde con el modelo en memoria.** Ninguna llamada a MLflow
   puede bloquear un pronóstico. "No hay conexión" nunca se trata como "no hay
   modelo".
7. **Los endpoints y los DAGs solo orquestan.** La lógica está en
   `src/novamercado/` y se prueba sin Docker, MLflow, Airflow ni PostgreSQL.
8. **Nada de datos ni credenciales en Git ni en las imágenes.** `datos/publicados/`
   y `.env` están en `.gitignore`; los parámetros de negocio van en
   `config/params.yaml`, no en el código.
9. **Versiones fijas** en las imágenes de Docker y en `requirements-servicio.txt`.

## Forma de trabajo

- Ramas `feature/<tema>` y Pull Request a `main`, que está protegida. El CI
  corre `pytest` en cada PR.
- `pytest -q` debe pasar antes de abrir un PR.
- Toda decisión técnica o de producto nueva se documenta en `DECISIONES.md` en
  el mismo PR, con sus alternativas y su justificación.
- Código, mensajes y documentación en español.
- Si se cambia código en `src/`, hay que reconstruir las imágenes:
  `docker compose up -d --build`.

## Comandos

```bash
source .venv/bin/activate
pytest -q
docker compose up -d --build                 # producto completo
curl -s localhost:8000/health
docker compose logs api --tail 50
python scripts/simular_operacion.py          # operación simulada y evidencia
bash scripts/probar_interrupcion_mlflow.sh
bash scripts/probar_reinicio.sh
```

## Mapa del código

| Módulo | Responsabilidad |
|---|---|
| `limpieza.py` | Reparar, advertir o rechazar datos de entrada |
| `esquemas.py` | Contrato (Pydantic) |
| `features.py` | Variables del modelo con información disponible |
| `modelo.py` | Baseline, LightGBM y cantidad sugerida por costos |
| `reentrenamiento.py` | Ventanas y criterio de reemplazo (sin servicios externos) |
| `registro.py` | MLflow: corridas, versiones y alias |
| `tareas.py` | Pasos que ejecuta el DAG |
| `servicio.py` / `api.py` | Lógica de los endpoints / HTTP |
| `db.py` | Tablas y consultas de PostgreSQL |
| `estado.py` | Modelo en memoria, recarga y `/health` |
