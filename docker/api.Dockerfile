# Imagen de la API y del inicializador del primer modelo.
FROM python:3.12.11-slim-bookworm

# libgomp1: LightGBM la necesita para entrenar y predecir.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-servicio.txt .
RUN pip install --no-cache-dir -r requirements-servicio.txt

COPY src ./src
COPY config ./config

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios; la carpeta guarda la copia local del modelo vigente.
RUN useradd --create-home app && mkdir -p /var/lib/novamercado/modelo && chown -R app /var/lib/novamercado
USER app

EXPOSE 8000
CMD ["uvicorn", "novamercado.api:app", "--host", "0.0.0.0", "--port", "8000"]
