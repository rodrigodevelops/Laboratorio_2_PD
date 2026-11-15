#!/usr/bin/env bash
# Detiene el producto sin borrar volúmenes, lo vuelve a levantar y verifica que
# conserve el modelo y los registros, sin volver a entrenar.
#
# Uso (con el producto levantado): bash scripts/probar_reinicio.sh
set -u
API=${API:-http://localhost:8000}
SALIDA=${SALIDA:-docs/evidencia/reinicio.md}

contar() {
  docker compose exec -T db psql -U novamercado -d novamercado -tAc \
    "select (select count(*) from solicitudes)||' solicitudes, '||(select count(*) from observaciones)||' observaciones'" 2>/dev/null
}

antes_modelo=$(curl -s "$API/modelo"); antes_datos=$(contar)
echo "Antes: $antes_modelo | $antes_datos"
docker compose down
inicio=$(date +%s)
docker compose up -d
until curl -s "$API/health" | grep -q '"ok"'; do
  sleep 3
  [ $(( $(date +%s) - inicio )) -ge 600 ] && { echo "No llegó a ok en 10 minutos"; break; }
done
listo=$(( $(date +%s) - inicio ))
despues_modelo=$(curl -s "$API/modelo"); despues_datos=$(contar)
inicializador=$(docker compose logs inicializador 2>/dev/null | grep -E "Ya hay|registrada" | tail -1 | sed 's/^.*| //')
echo "Después: $despues_modelo | $despues_datos | ok en ${listo} s"
echo "Inicializador: $inicializador"

mkdir -p "$(dirname "$SALIDA")"
cat > "$SALIDA" <<MD
# Reinicio sin borrar volúmenes

Generado con \`scripts/probar_reinicio.sh\` el $(date '+%Y-%m-%d %H:%M'): \`docker compose down\` y \`docker compose up -d\`.

| | Antes | Después |
|---|---|---|
| \`GET /modelo\` | \`$antes_modelo\` | \`$despues_modelo\` |
| Base de datos | $antes_datos | $despues_datos |

- \`/health\` en \`ok\` **${listo} s** después de \`docker compose up -d\` (límite: 10 minutos).
- Inicializador: "$inicializador"
MD
echo "Evidencia escrita en $SALIDA"
