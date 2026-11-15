# Reinicio sin borrar volúmenes

Generado con `scripts/probar_reinicio.sh` el 2026-11-14 10:57: `docker compose down` y `docker compose up -d`.

| | Antes | Después |
|---|---|---|
| `GET /modelo` | `{"nombre":"novamercado-ventas","alias":"vigente","version":"2"}` | `{"nombre":"novamercado-ventas","alias":"vigente","version":"2"}` |
| Base de datos | 591 solicitudes, 3354 observaciones | 591 solicitudes, 3354 observaciones |

- `/health` en `ok` **39 s** después de `docker compose up -d` (límite: 10 minutos).
- Inicializador: "Ya hay un modelo vigente (versión 2); no se entrena de nuevo."
