# Evidencia de funcionamiento

| Archivo | Qué muestra |
|---|---|
| `operacion.md` | Operación simulada de 28 días: costo de las sugerencias por semana y versión del modelo, reentrenamientos (promovidos y no promovidos, con su motivo) y ejemplos de respuestas a solicitudes válidas, corregidas, con advertencia y rechazadas |
| `interrupcion_mlflow.md` | La API sigue respondiendo con MLflow detenido; tiempos de `/health` hasta `degradado` y de vuelta |
| `reinicio.md` | Detener y levantar sin borrar volúmenes: se conservan el modelo y los registros, sin volver a entrenar |
| `mlflow_experimento.png` | Corridas del experimento `novamercado` (primer modelo y reentrenamientos) |
| `mlflow_versiones.png` | Versiones de `novamercado-ventas` con el alias `vigente` |
| `airflow_dag.png` | Ejecuciones del DAG `reentrenamiento` y sus tareas |
