# Prueba de operación simulada

Generado con `scripts/simular_operacion.py`: 28 días desde 2026-03-01, 25% de solicitudes con defectos, reentrenamiento cada 7 días, cambio de demanda desde 2026-03-08 (bebidas=1.5,snacks=1.5).

## Costo de las sugerencias por semana

| Semana | Versión | Costo | Ventas reales | Costo por unidad vendida | WAPE |
|---|---|---|---|---|---|
| 2026-02-23 | 1 | 3,860 | 26,876 | 0.144 | 0.168 |
| 2026-03-02 | 1 | 20,839 | 172,543 | 0.121 | 0.170 |
| 2026-03-09 | 1 | 30,228 | 198,104 | 0.153 | 0.227 |
| 2026-03-16 | 1 | 21,263 | 161,102 | 0.132 | 0.201 |
| 2026-03-16 | 2 | 3,954 | 27,911 | 0.142 | 0.186 |
| 2026-03-23 | 2 | 18,308 | 156,663 | 0.117 | 0.176 |

**Total:** costo 98,452 sobre 743,199 unidades vendidas.

## Reentrenamientos

| Fecha simulada | Estado | Promovido | Versión | Duración | Motivo |
|---|---|---|---|---|---|
| 2026-03-08 | exitoso | False | 1 | 25 s | Costo en validación 20 844 vs 21 064 del vigente (7 días): no alcanza la mejora mínima de 2% |
| 2026-03-15 | exitoso | False | 1 | 20 s | Costo en validación 29 934 vs 29 513 del vigente (7 días): no alcanza la mejora mínima de 2% |
| 2026-03-22 | exitoso | True | 2 | 20 s | Costo en validación 22 819 vs 25 492 del vigente (7 días): 10.5% menos |
| 2026-03-29 | exitoso | False | 2 | 15 s | Costo en validación 22 451 vs 22 248 del vigente (7 días): no alcanza la mejora mínima de 2% |

## Respuestas por estado

- observaciones 200 advertencia: 18
- observaciones 200 corregido: 57
- observaciones 200 ok: 205
- observaciones reenviadas: 14
- prediccion 200 advertencia: 34
- prediccion 200 corregido: 45
- prediccion 200 ok: 201

## Defectos enviados

- observación: familia escrita distinto: 14
- observación: ventas con coma decimal: 23
- observación: ventas con separador de miles: 20
- observación: ventas negativas: 18
- pronóstico: campo de tienda renombrado: 1
- pronóstico: campo extra desconocido: 8
- pronóstico: faltan dos familias: 7
- pronóstico: familia en mayúsculas y con tildes: 8
- pronóstico: familia repetida: 9
- pronóstico: fecha con hora: 6
- pronóstico: fecha en formato AAAA/MM/DD: 4
- pronóstico: promoción ausente: 10
- pronóstico: promoción como texto: 8
- pronóstico: promoción decimal: 4
- pronóstico: tienda como texto con espacios: 10
- pronóstico: tienda con prefijo: 8

## Ejemplos de solicitudes y respuestas

### catálogo: E01_tienda_texto

Solicitud:

```json
{
  "tienda_id": "T05",
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "tienda_id",
        "accion": "reparar",
        "detalle": "'T05' se interpretó como 5"
      }
    ]
  }
}
```

### catálogo: E02_familia_otra_forma

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "familias[5].familia_id",
        "accion": "reparar",
        "detalle": "'Frutas y Verduras' se interpretó como 'frutas_verduras'"
      },
      {
        "campo": "familias[6].familia_id",
        "accion": "reparar",
        "detalle": "'LÁCTEOS' se interpretó como 'lacteos'"
      }
    ]
  }
}
```

### catálogo: E03_promocion_texto

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8.0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "familias[11].en_promocion",
        "accion": "reparar",
        "detalle": "'9' se interpretó como 9"
      }
    ]
  }
}
```

### catálogo: E04_fecha_formato

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "17/11/2025",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "fecha",
        "accion": "reparar",
        "detalle": "'17/11/2025' se interpretó como '2025-11-17' (día/mes/año)"
      }
    ]
  }
}
```

### catálogo: E05_faltan_familias

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    {
      "familia_id": "carnes",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "familias",
        "accion": "advertir",
        "detalle": "no se recibieron bebe, mascotas; se pronosticaron asumiendo 0 productos en promoción"
      }
    ]
  }
}
```

### catálogo: E06_familia_repetida

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 1065.4,
      "cantidad_sugerida": 1338
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "familias[12]",
        "accion": "advertir",
        "detalle": "'abarrotes' repetida con valores distintos (familias[0]: 0, familias[12]: 3); se usó la última aparición"
      }
    ]
  }
}
```

### catálogo: E07_campo_renombrado

Solicitud:

```json
{
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ],
  "tienda": 5
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "tienda_id",
        "accion": "reparar",
        "detalle": "campo 'tienda' se interpretó como 'tienda_id'"
      }
    ]
  }
}
```

### catálogo: E08_ventas_negativas

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 994
    },
    {
      "familia_id": "bebe",
      "ventas": 50
    },
    {
      "familia_id": "bebidas",
      "ventas": 1292
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 11,
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "ventas[5].ventas",
        "accion": "advertir",
        "detalle": "-4 es negativo (posible devolución); se desconoce la venta real y no se guardó"
      }
    ]
  }
}
```

### catálogo: E09_envio_repetido

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 994
    },
    {
      "familia_id": "bebe",
      "ventas": 50
    },
    {
      "familia_id": "bebidas",
      "ventas": 1292
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 1,
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### catálogo: E10_numero_formato

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 994
    },
    {
      "familia_id": "bebe",
      "ventas": "50,0"
    },
    {
      "familia_id": "bebidas",
      "ventas": "1,292"
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 0,
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "ventas[1].ventas",
        "accion": "reparar",
        "detalle": "'50,0' se interpretó como 50"
      },
      {
        "campo": "ventas[2].ventas",
        "accion": "reparar",
        "detalle": "'1,292' se interpretó como 1292"
      }
    ]
  }
}
```

### catálogo: observacion_valida

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 994
    },
    {
      "familia_id": "bebe",
      "ventas": 50
    },
    {
      "familia_id": "bebidas",
      "ventas": 1292
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 0,
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### catálogo: prediccion_valida

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 8
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 942.4,
      "cantidad_sugerida": 1184
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 61.6,
      "cantidad_sugerida": 84
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1020.0,
      "cantidad_sugerida": 1281
    },
    "…"
  ],
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### rechazo: tienda inexistente

Solicitud:

```json
{
  "tienda_id": 99,
  "fecha": "2026-03-01",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    }
  ]
}
```

Respuesta (HTTP 422):

```json
{
  "detail": "la tienda 99 no existe"
}
```

### rechazo: fecha ambigua

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "05/03/2026",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    }
  ]
}
```

Respuesta (HTTP 422):

```json
{
  "detail": "la fecha '05/03/2026' es ambigua: puede ser día/mes o mes/día; se espera AAAA-MM-DD"
}
```

### rechazo: número en el nombre de otra tienda

Solicitud:

```json
{
  "tienda_id": "Zona 10",
  "fecha": "2026-03-01",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    }
  ]
}
```

Respuesta (HTTP 422):

```json
{
  "detail": "no se pudo determinar la tienda a partir de 'Zona 10'"
}
```

### rechazo: sin familias válidas

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-01",
  "familias": [
    {
      "familia_id": "electronica",
      "en_promocion": 1
    }
  ]
}
```

Respuesta (HTTP 422):

```json
{
  "detail": "la solicitud no contiene ninguna familia de producto válida"
}
```

### pronóstico válido

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-01",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 4
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-01",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 812.6,
      "cantidad_sugerida": 1021
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 89.2,
      "cantidad_sugerida": 121
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 882.9,
      "cantidad_sugerida": 1109
    },
    "…"
  ],
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### pronóstico: promoción ausente

Solicitud:

```json
{
  "tienda_id": 2,
  "fecha": "2026-03-28",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 9
    },
    {
      "familia_id": "bebe"
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 2
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 2,
  "fecha": "2026-03-28",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 605.0,
      "cantidad_sugerida": 727
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 39.7,
      "cantidad_sugerida": 52
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 522.0,
      "cantidad_sugerida": 805
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "familias[1].en_promocion",
        "accion": "advertir",
        "detalle": "no se informó; se asumió 0 productos en promoción"
      }
    ]
  }
}
```

### pronóstico: faltan dos familias

Solicitud:

```json
{
  "tienda_id": 3,
  "fecha": "2026-03-19",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 12
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 4
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 3,
  "fecha": "2026-03-19",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 919.7,
      "cantidad_sugerida": 1155
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 48.7,
      "cantidad_sugerida": 66
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1024.4,
      "cantidad_sugerida": 1287
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "familias",
        "accion": "advertir",
        "detalle": "no se recibieron panaderia, snacks; se pronosticaron asumiendo 0 productos en promoción"
      }
    ]
  }
}
```

### pronóstico: familia repetida

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-26",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-26",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 740.3,
      "cantidad_sugerida": 889
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 65.9,
      "cantidad_sugerida": 85
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 616.7,
      "cantidad_sugerida": 951
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "familias[12]",
        "accion": "advertir",
        "detalle": "'abarrotes' repetida con valores distintos (familias[0]: 0, familias[12]: 3); se usó la última aparición"
      }
    ]
  }
}
```

### pronóstico: tienda como texto con espacios

Solicitud:

```json
{
  "tienda_id": " 8 ",
  "fecha": "2026-03-27",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 8,
  "fecha": "2026-03-27",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 548.4,
      "cantidad_sugerida": 659
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 44.5,
      "cantidad_sugerida": 58
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 430.4,
      "cantidad_sugerida": 664
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "tienda_id",
        "accion": "reparar",
        "detalle": "' 8 ' se interpretó como 8"
      }
    ]
  }
}
```

### observación: ventas con coma decimal

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-28",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": "1368,0"
    },
    {
      "familia_id": "bebe",
      "ventas": 65.0
    },
    {
      "familia_id": "bebidas",
      "ventas": 1074.0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 12,
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "ventas[0].ventas",
        "accion": "reparar",
        "detalle": "'1368,0' se interpretó como 1368"
      }
    ]
  }
}
```

### observación reenviada (idempotencia)

Solicitud:

```json
{
  "tienda_id": 3,
  "fecha": "2026-03-01",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 1157.0
    },
    {
      "familia_id": "bebe",
      "ventas": 73.0
    },
    {
      "familia_id": "bebidas",
      "ventas": 987.0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 0,
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### observación: ventas con separador de miles

Solicitud:

```json
{
  "tienda_id": 5,
  "fecha": "2026-03-28",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": "2,008"
    },
    {
      "familia_id": "bebe",
      "ventas": "59"
    },
    {
      "familia_id": "bebidas",
      "ventas": "1,396"
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 12,
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "ventas[0].ventas",
        "accion": "reparar",
        "detalle": "'2,008' se interpretó como 2008"
      },
      {
        "campo": "ventas[1].ventas",
        "accion": "reparar",
        "detalle": "'59' se interpretó como 59"
      },
      {
        "campo": "ventas[2].ventas",
        "accion": "reparar",
        "detalle": "'1,396' se interpretó como 1396"
      },
      {
        "campo": "ventas[3].ventas",
        "accion": "reparar",
        "detalle": "'389' se interpretó como 389"
      },
      {
        "campo": "ventas[4].ventas",
        "accion": "reparar",
        "detalle": "'222' se interpretó como 222"
      },
      {
        "campo": "ventas[5].ventas",
        "accion": "reparar",
        "detalle": "'408' se interpretó como 408"
      },
      {
        "campo": "ventas[6].ventas",
        "accion": "reparar",
        "detalle": "'635' se interpretó como 635"
      },
      {
        "campo": "ventas[7].ventas",
        "accion": "reparar",
        "detalle": "'104' se interpretó como 104"
      },
      {
        "campo": "ventas[8].ventas",
        "accion": "reparar",
        "detalle": "'325' se interpretó como 325"
      },
      {
        "campo": "ventas[9].ventas",
        "accion": "reparar",
        "detalle": "'54' se interpretó como 54"
      },
      {
        "campo": "ventas[10].ventas",
        "accion": "reparar",
        "detalle": "'494' se interpretó como 494"
      },
      {
        "campo": "ventas[11].ventas",
        "accion": "reparar",
        "detalle": "'722' se interpretó como 722"
      }
    ]
  }
}
```

### pronóstico: familia en mayúsculas y con tildes

Solicitud:

```json
{
  "tienda_id": 6,
  "fecha": "2026-03-20",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 5
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "BEBIDAS",
      "en_promocion": 1
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 6,
  "fecha": "2026-03-20",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 530.0,
      "cantidad_sugerida": 666
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 29.4,
      "cantidad_sugerida": 40
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 468.7,
      "cantidad_sugerida": 589
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "familias[2].familia_id",
        "accion": "reparar",
        "detalle": "'BEBIDAS' se interpretó como 'bebidas'"
      }
    ]
  }
}
```

### observación: ventas negativas

Solicitud:

```json
{
  "tienda_id": 6,
  "fecha": "2026-03-25",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 325.0
    },
    {
      "familia_id": "bebe",
      "ventas": 24.0
    },
    {
      "familia_id": "bebidas",
      "ventas": 760.0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 11,
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "ventas[4].ventas",
        "accion": "advertir",
        "detalle": "-3 es negativo (posible devolución); se desconoce la venta real y no se guardó"
      }
    ]
  }
}
```

### pronóstico: campo extra desconocido

Solicitud:

```json
{
  "tienda_id": 10,
  "fecha": "2026-03-28",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 4
    },
    "…"
  ],
  "canal": "pos-v2"
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 10,
  "fecha": "2026-03-28",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 83.3,
      "cantidad_sugerida": 100
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 4.6,
      "cantidad_sugerida": 6
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 209.3,
      "cantidad_sugerida": 323
    },
    "…"
  ],
  "calidad": {
    "estado": "advertencia",
    "observaciones": [
      {
        "campo": "canal",
        "accion": "advertir",
        "detalle": "campo 'canal' no pertenece al contrato; se ignoró"
      }
    ]
  }
}
```

### pronóstico: fecha con hora

Solicitud:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-25T00:00:00",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 2
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-25",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 578.9,
      "cantidad_sugerida": 695
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 71.6,
      "cantidad_sugerida": 93
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 610.3,
      "cantidad_sugerida": 941
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "fecha",
        "accion": "reparar",
        "detalle": "'2026-03-25T00:00:00' se interpretó como '2026-03-25'"
      }
    ]
  }
}
```

### observación: familia escrita distinto

Solicitud:

```json
{
  "tienda_id": 3,
  "fecha": "2026-03-27",
  "ventas": [
    {
      "familia_id": "abarrotes",
      "ventas": 1127.0
    },
    {
      "familia_id": "bebe",
      "ventas": 49.0
    },
    {
      "familia_id": "bebidas",
      "ventas": 939.0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "registros_guardados": 12,
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "ventas[5].familia_id",
        "accion": "reparar",
        "detalle": "'FRUTAS_VERDURAS' se interpretó como 'frutas_verduras'"
      }
    ]
  }
}
```

### pronóstico: tienda con prefijo

Solicitud:

```json
{
  "tienda_id": "T09",
  "fecha": "2026-03-26",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 2
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 9,
  "fecha": "2026-03-26",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 130.5,
      "cantidad_sugerida": 157
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 5.0,
      "cantidad_sugerida": 7
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 295.7,
      "cantidad_sugerida": 456
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "tienda_id",
        "accion": "reparar",
        "detalle": "'T09' se interpretó como 9"
      }
    ]
  }
}
```

### pronóstico: promoción decimal

Solicitud:

```json
{
  "tienda_id": 7,
  "fecha": "2026-03-26",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 7,
  "fecha": "2026-03-26",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 578.7,
      "cantidad_sugerida": 695
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 31.5,
      "cantidad_sugerida": 41
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 384.5,
      "cantidad_sugerida": 593
    },
    "…"
  ],
  "calidad": {
    "estado": "ok",
    "observaciones": []
  }
}
```

### pronóstico: fecha en formato AAAA/MM/DD

Solicitud:

```json
{
  "tienda_id": 2,
  "fecha": "2026/03/27",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 10
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 4
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 2,
  "fecha": "2026-03-27",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 569.9,
      "cantidad_sugerida": 684
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 36.5,
      "cantidad_sugerida": 47
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 566.7,
      "cantidad_sugerida": 874
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "fecha",
        "accion": "reparar",
        "detalle": "'2026/03/27' se interpretó como '2026-03-27'"
      }
    ]
  }
}
```

### pronóstico: promoción como texto

Solicitud:

```json
{
  "tienda_id": 7,
  "fecha": "2026-03-28",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": "8"
    },
    {
      "familia_id": "bebe",
      "en_promocion": 0
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 0
    },
    "…"
  ]
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 7,
  "fecha": "2026-03-28",
  "version_modelo": "2",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 836.2,
      "cantidad_sugerida": 1004
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 43.6,
      "cantidad_sugerida": 57
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 505.1,
      "cantidad_sugerida": 779
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "familias[0].en_promocion",
        "accion": "reparar",
        "detalle": "'8' se interpretó como 8"
      }
    ]
  }
}
```

### pronóstico: campo de tienda renombrado

Solicitud:

```json
{
  "fecha": "2026-03-13",
  "familias": [
    {
      "familia_id": "abarrotes",
      "en_promocion": 0
    },
    {
      "familia_id": "bebe",
      "en_promocion": 1
    },
    {
      "familia_id": "bebidas",
      "en_promocion": 9
    },
    "…"
  ],
  "tienda": 5
}
```

Respuesta (HTTP 200):

```json
{
  "tienda_id": 5,
  "fecha": "2026-03-13",
  "version_modelo": "1",
  "predicciones": [
    {
      "familia_id": "abarrotes",
      "venta_esperada": 1067.7,
      "cantidad_sugerida": 1341
    },
    {
      "familia_id": "bebe",
      "venta_esperada": 90.5,
      "cantidad_sugerida": 123
    },
    {
      "familia_id": "bebidas",
      "venta_esperada": 1311.3,
      "cantidad_sugerida": 1647
    },
    "…"
  ],
  "calidad": {
    "estado": "corregido",
    "observaciones": [
      {
        "campo": "tienda_id",
        "accion": "reparar",
        "detalle": "campo 'tienda' se interpretó como 'tienda_id'"
      }
    ]
  }
}
```
