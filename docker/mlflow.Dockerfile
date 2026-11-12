# Servidor de MLflow con el controlador de PostgreSQL.
# SQLAlchemy 2.1 usa psycopg (versión 3) por defecto para postgresql://
FROM python:3.12.11-slim-bookworm
RUN pip install --no-cache-dir mlflow==3.18.0 "psycopg[binary]==3.3.8"
EXPOSE 5000
