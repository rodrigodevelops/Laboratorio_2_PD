#!/usr/bin/env bash
# Detiene MLflow, verifica que la API siga respondiendo y que /health lo refleje,
# y mide cuánto tarda en volver a "ok" cuando MLflow regresa.
# Requisito: /health degradado en menos de 1 minuto y ok en menos de 2.
#
# Uso (con el producto levantado): bash scripts/probar_interrupcion_mlflow.sh
set -u
API=${API:-http://localhost:8000}
SALIDA=${SALIDA:-docs/evidencia/interrupcion_mlflow.md}
EJEMPLO=${EJEMPLO:-datos/publicados/ejemplos/prediccion_valida.json}

salud() { curl -s "$API/health"; }
esperar() {  # esperar <texto que debe aparecer o desaparecer> <aparecer|desaparecer> <límite en s>
  local inicio=$(date +%s)
  while true; do
    if [ "$2" = aparecer ] && salud | grep -q "$1"; then break; fi
    if [ "$2" = desaparecer ] && ! salud | grep -q "$1"; then break; fi
    [ $(( $(date +%s) - inicio )) -ge "$3" ] && { echo "TIEMPO_AGOTADO"; return; }
    sleep 1
  done
  echo $(( $(date +%s) - inicio ))
}

inicial=$(salud)
echo "Salud inicial: $inicial"
docker compose stop mlflow >/dev/null 2>&1
echo "MLflow detenido."
t_degradado=$(esperar MLflow aparecer 120)
durante=$(salud)
codigo=$(curl -s -o /tmp/prediccion_sin_mlflow.json -w "%{http_code}" -X POST "$API/v1/prediccion" \
  -H "content-type: application/json" -d @"$EJEMPLO")
version=$(python3 -c "import json;print(json.load(open('/tmp/prediccion_sin_mlflow.json')).get('version_modelo'))" 2>/dev/null)
echo "Degradado en ${t_degradado} s. Pronóstico con MLflow detenido: HTTP $codigo, versión $version"

docker compose start mlflow >/dev/null 2>&1
echo "MLflow iniciado."
t_ok=$(esperar MLflow desaparecer 240)
final=$(salud)
echo "Sin MLflow en el motivo tras ${t_ok} s: $final"

mkdir -p "$(dirname "$SALIDA")"
cat > "$SALIDA" <<MD
# Interrupción de MLflow

Generado con \`scripts/probar_interrupcion_mlflow.sh\` el $(date '+%Y-%m-%d %H:%M').

| Momento | Resultado |
|---|---|
| Antes | \`$inicial\` |
| MLflow detenido (\`docker compose stop mlflow\`) | \`/health\` degradado en **${t_degradado} s** (límite: 60 s) |
| Durante | \`$durante\` |
| Pronóstico con MLflow detenido | HTTP **$codigo**, \`version_modelo\` $version |
| MLflow iniciado (\`docker compose start mlflow\`) | \`/health\` sin MLflow en el motivo en **${t_ok} s** (límite: 120 s) |
| Después | \`$final\` |
MD
echo "Evidencia escrita en $SALIDA"
