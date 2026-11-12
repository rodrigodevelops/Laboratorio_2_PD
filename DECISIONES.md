# Decisiones técnicas y de producto

Cada decisión incluye las alternativas consideradas y su justificación. Este
documento se actualiza en el mismo Pull Request que introduce cada decisión.

---

## 1. Política ante datos defectuosos

### 1.1 Principios

Las reglas son por **tipo de campo**, no por ejemplo del catálogo, porque el
servicio recibirá problemas que no se han visto. Se aplican tres acciones:

- **Reparar:** hay una sola interpretación posible y la corrección no cambia el
  significado (por ejemplo, `"T05"` → `5` o `"LÁCTEOS"` → `lacteos`).
- **Advertir:** se responde, pero suponiendo algo, y se informa qué se supuso.
- **Rechazar (422):** no se puede saber qué se pide.

**Regla de identidad:** la tienda y la fecha identifican la solicitud. Solo se
reparan o se rechazan; nunca se suponen, porque responder con una tienda o una
fecha supuesta sería inventar datos. Los datos de cada familia se reparan o se
advierten: un problema en una familia nunca invalida toda la solicitud.

`calidad.estado` es `advertencia` si hay al menos una acción `advertir`,
`corregido` si solo hay `reparar`, y `ok` si no hay observaciones. El modelo de
Pydantic `Calidad` impide construir una respuesta incoherente.

La limpieza vive en `src/novamercado/limpieza.py` y sus pruebas en
`tests/test_limpieza.py`. Los endpoints solo la llaman. El resultado de la
limpieza se valida con modelos estrictos de Pydantic (`esquemas.py`).

### 1.2 Predicción (`POST /v1/prediccion`)

| Campo | Problema | Política |
|---|---|---|
| Nombres de campo | Distintos al contrato (`tienda`, `Fecha`, `id_tienda`) (E07) | **Reparar** si el nombre normalizado coincide con el contrato o con un sinónimo conocido |
| | Dos nombres para la tienda o la fecha con valores distintos | **Rechazar** |
| | Campos desconocidos | **Advertir**: se ignoran |
| `tienda_id` | Texto, prefijo corto o decimal entero (`"5"`, `"T05"`, `"tienda 5"`, `5.0`) (E01) | **Reparar** |
| | Nombre completo de la tienda según `tiendas.csv` | **Reparar** |
| | Número dentro de otro texto (`"Zona 10"`), inexistente o ilegible | **Rechazar** |
| `fecha` | Formato inequívoco distinto (`…T00:00:00`, `17/11/2025`, `20251117`) (E04) | **Reparar** |
| | Ambigua (`05/11/2025`: puede ser día/mes o mes/día) | **Rechazar** |
| | Ilegible, inexistente o anterior a la apertura de la tienda | **Rechazar** |
| `familia_id` | Mayúsculas, tildes, espacios o nombre legible (E02) | **Reparar** al compararla normalizada con `familias.csv` |
| | Muy parecida a una sola familia (`"lacteo"`) | **Advertir**: se usa esa familia |
| | Desconocida | **Advertir**: se omite |
| `en_promocion` | Texto o decimal entero (`"3"`, `2.0`) (E03) | **Reparar** |
| | Ausente, negativa, ilegible o ambigua (`"1.000"`) | **Advertir**: se asume 0 |
| | Decimal no entero | **Advertir**: se redondea |
| Lista de familias | Faltan familias (E05) | **Advertir**: se pronostican las 12, con promoción 0 en las faltantes |
| | Familia repetida con valores iguales | **Reparar**: se toma una vez |
| | Familia repetida con valores distintos (E06) | **Advertir**: se usa la última aparición |
| | Vacía, ausente o sin ninguna familia válida | **Rechazar** |
| Cuerpo | No es un objeto JSON | **Rechazar** |

### 1.3 Observaciones (`POST /v1/observaciones`)

| Campo | Problema | Política |
|---|---|---|
| Tienda, fecha, nombres de campo | Igual que en predicción | Igual que en predicción |
| `ventas` | Separador de miles o coma decimal (`"1,234"`, `"812,0"`) (E10) | **Reparar**: coma seguida de grupos de 3 dígitos es separador de miles; de 1 o 2 dígitos, decimal; con punto y coma, el último es el decimal |
| | Punto con exactamente tres decimales (`"1.234"`) | **Advertir**: es ambiguo y el registro no se guarda |
| | Negativas (E08) | **Advertir**: el registro no se guarda |
| | Ausentes o ilegibles | **Advertir**: el registro no se guarda |
| | Decimal no entero | **Advertir**: se redondea |
| Lista | Faltan familias | **Advertir**: se guardan las recibidas |
| | Familia repetida con valores distintos | **Advertir**: se usa la última aparición |

### 1.4 Decisiones discutidas

**Faltan familias (E05): se pronostican las 12.** La tienda vende las 12 y
necesita el pronóstico completo para preparar su inventario. Las faltantes se
pronostican con promoción 0 y se advierte. *Alternativa:* pronosticar solo las
recibidas; se descartó porque deja a la tienda sin información que sí puede
calcularse.

**Familia repetida con valores distintos (E06): se usa la última.** Se interpreta
la segunda aparición como una corrección del sistema de la tienda. *Alternativa:*
rechazar la solicitud; se descartó porque un error en una familia dejaría sin
pronóstico a las otras once.

**Ventas negativas (E08): no se guardan.** Según el catálogo son devoluciones
registradas como venta, así que se desconoce la venta real. Guardar 0 o el valor
negativo contaminaría el reentrenamiento. *Alternativa:* guardar 0; se descartó
porque es un dato inventado.

**Tienda: solo un número con prefijo corto, o el nombre completo.** Una versión
anterior tomaba cualquier número dentro del texto, pero los nombres de las
tiendas contienen números: `"NovaMercado Zona 10"` es la tienda 1 y se habría
interpretado como la 10. Darle a una tienda el pronóstico de otra es el peor
error posible, porque se reporta como reparado y nadie lo nota. Por eso el texto
debe ser un identificador (`"T05"`, `"tienda 5"`) o el nombre exacto; cualquier
otra cosa se rechaza.

**Fecha ambigua: se rechaza.** `05/11/2025` puede ser 5 de noviembre o 11 de
mayo. Suponer día/mes/año (la convención en Guatemala) contradiría la regla de
identidad: la fecha nunca se supone. Se consideró suponerla con advertencia, pero
un error de interpretación daría el pronóstico de otro día marcado como válido.
Las fechas en que una parte es mayor que 12, o en que día y mes coinciden, no
son ambiguas y se reparan.

**Número con punto y tres decimales: ambiguo.** Con la convención local,
`"1.234"` es uno coma dos; leído como unidades enteras, es mil doscientos treinta
y cuatro. Las dos lecturas razonables no coinciden, así que no se guarda. En
cambio, `"1,234"` no es ambiguo: como separador de miles (convención local) y
como entero dan lo mismo. Guardar el valor equivocado contaminaría el
reentrenamiento con un dato mil veces menor.

**Observaciones repetidas con valores distintos: gana la que llega después.**
Las tiendas no envían una marca de tiempo, así que no se puede saber cuál es más
reciente en origen. Si un sistema reenvía con retraso un mensaje viejo, pisaría
una corrección. Es una limitación conocida; cada cambio queda registrado en la
base de datos para poder auditarlo.

**No se usa el reloj del sistema.** Las fechas son simuladas: una fecha futura o
lejana no se rechaza por ser futura. El único límite temporal es la fecha de
apertura de la tienda.
