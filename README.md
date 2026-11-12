# NovaMercado: pronóstico diario de ventas

Servicio de machine learning que, cada mañana, pronostica las ventas del día por
familia de producto para cada tienda de NovaMercado y sugiere cuánto tener
disponible. Defiende su contrato ante datos defectuosos, registra lo que predice
y lo que ocurre, y reentrena su modelo con esa información.

Las decisiones técnicas y de producto están en [DECISIONES.md](DECISIONES.md).

| Componente | Tecnología | Dirección |
|---|---|---|
| API | FastAPI | <http://localhost:8000> (documentación en `/docs`) |
| Base de datos del producto | PostgreSQL 16 | interna (`db`) |
| Experimentos y modelos | MLflow 3 | <http://localhost:5000> |
| Reentrenamiento | Airflow 3 | <http://localhost:8080> |

---

## Levantar el producto desde cero

### Requisitos

- Docker con Docker Compose v2.14 o superior. En Windows, Docker Desktop con WSL 2 y
  al menos 6 GB de memoria disponibles.
- Git.

### 1. Clonar el repositorio

```bash
git clone https://github.com/rodrigodevelops/Laboratorio_2_PD.git
cd Laboratorio_2_PD
```

### 2. Colocar los archivos publicados

Copiar el contenido del archivo publicado en **`datos/publicados/`**, de modo que
queden así:

```
datos/publicados/tiendas.csv
datos/publicados/familias.csv
datos/publicados/historico_ventas.csv
datos/publicados/feriados.csv
datos/publicados/costos.csv
datos/publicados/catalogo_errores.md      (opcional)
datos/publicados/ejemplos/                (opcional)
```

### 3. Crear el archivo de credenciales

```bash
cp .env.example .env
```

Los valores de ejemplo funcionan para una instalación local. Las credenciales no
están en el repositorio ni en las imágenes.

### 4. Levantar

```bash
docker compose up -d --build
```

La primera vez, Docker construye las imágenes (varios minutos). Después, sin
intervención manual:

1. Arrancan PostgreSQL, MLflow y Airflow.
2. El servicio `inicializador` carga los datos publicados, entrena el primer
   modelo, lo compara con el baseline, lo registra en MLflow con el alias
   `vigente` y termina.
3. La API detecta el modelo y empieza a responder.

### 5. Verificar

```bash
curl http://localhost:8000/health
```

Responde `{"estado": "ok", ...}` cuando todo está listo, normalmente en 2 a 4
minutos (sin contar la construcción de las imágenes). Mientras no haya un modelo
cargado responde 503.

### Detener y volver a levantar

```bash
docker compose down        # conserva los datos (volúmenes)
docker compose up -d       # retoma con el mismo modelo y los mismos registros
```

Al volver a levantarse, el inicializador detecta que ya hay un modelo vigente y
no entrena de nuevo. Para borrar todo y empezar de cero:
`docker compose down --volumes`.

---

## Uso

### Pronóstico

```bash
curl -X POST http://localhost:8000/v1/prediccion \
  -H "content-type: application/json" \
  -d @datos/publicados/ejemplos/prediccion_valida.json
```

### Ventas reales

```bash
curl -X POST http://localhost:8000/v1/observaciones \
  -H "content-type: application/json" \
  -d @datos/publicados/ejemplos/observacion_valida.json
```

### Modelo vigente y reentrenamiento

```bash
curl http://localhost:8000/modelo
curl -X POST http://localhost:8000/admin/reentrenar          # devuelve {"id": "..."}
curl http://localhost:8000/admin/reentrenar/<id>
```

---

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Las pruebas no necesitan Docker, MLflow, Airflow ni los datos publicados: usan
datos sintéticos y SQLite. En Linux o WSL, LightGBM requiere
`sudo apt install libgomp1`.

## Estructura

```
├── src/novamercado/      # todo el código del producto
│   ├── limpieza.py       #   política ante datos defectuosos
│   ├── esquemas.py       #   contrato (Pydantic)
│   ├── features.py       #   variables del modelo
│   ├── modelo.py         #   baseline, LightGBM y cantidad sugerida
│   ├── reentrenamiento.py#   criterio de reemplazo
│   ├── registro.py       #   MLflow
│   ├── servicio.py       #   lógica de los endpoints
│   ├── api.py            #   FastAPI
│   ├── db.py             #   PostgreSQL
│   └── estado.py         #   modelo en memoria y salud de las dependencias
├── dags/                 # DAG de reentrenamiento
├── docker/               # Dockerfiles e inicialización de PostgreSQL
├── config/params.yaml    # parámetros de producto y modelo
├── tests/
├── docker-compose.yaml
├── .env.example
├── CLAUDE.md
└── DECISIONES.md
```
