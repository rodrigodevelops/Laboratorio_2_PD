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

**Valores absurdos en las observaciones.** Una venta mayor que 10 veces el
máximo histórico de esa tienda y familia se guarda marcada como dudosa, con
advertencia, y no se usa para entrenar (`plausibilidad.py`). El umbral es amplio
a propósito: un cambio real de demanda no multiplica las ventas por diez de un
día para otro, pero un cero de más sí. *Alternativa:* no revisar plausibilidad;
se descartó porque un solo error de digitación contaminaría el reentrenamiento.

---

## 2. Información que usa el modelo al predecir

Al pronosticar el día D solo se usa información disponible antes de la solicitud:

| Información | Origen | Detalle |
|---|---|---|
| Ventas hasta D−1 | Histórico y observaciones registradas | Venta de D−1, D−7 y D−14; medias de 7 y 28 días; media del mismo día de la semana en las 4 semanas previas; días desde la última venta conocida |
| Promoción del día D | La solicitud de pronóstico | Las observaciones no la incluyen |
| Calendario | `feriados.csv` | Día de la semana, día del mes, mes, y si es feriado, fecha comercial, día de pago o medio día, según la ciudad de la tienda (`ambito`) |
| Tienda | `tiendas.csv` | Identificador y formato (hipermercado, supermercado, express) |
| Familia | `familias.csv` | Identificador |

Todas las variables de ventas pasan por un desplazamiento de un día sobre una
grilla diaria completa: la venta del propio día D nunca entra en sus variables.
La prueba `test_features_no_usan_el_futuro` cambia las ventas de D en adelante y
verifica que las variables no cambian.

Si falta la observación de algún día, las variables correspondientes quedan
vacías y LightGBM las maneja; `dias_desde_ultima` le indica al modelo cuánto
hace que no recibe datos. Como el modelo depende de las ventas recientes, se
adapta a cambios de demanda incluso antes de reentrenarse.

Para las ventas que llegan como observaciones, la promoción se toma de la última
solicitud de pronóstico de esa tienda, fecha y familia; si no hubo solicitud,
queda vacía.

---

## 3. Modelos y cantidad sugerida

### 3.1 Modelos

- **Baseline:** promedio de las ventas del mismo día de la semana en las 4
  semanas previas.
- **LightGBM:** un modelo global para todas las tiendas y familias, con
  objetivo Tweedie (adecuado para conteos positivos con cola larga).

En los últimos 56 días del histórico, reservados para la prueba:

| Modelo | WAPE | Costo de la cantidad sugerida |
|---|---|---|
| Baseline | 0.282 | 290 927 |
| LightGBM | 0.179 | 173 487 (40 % menos) |

Esta comparación se recalcula y se registra en MLflow cada vez que el producto
entrena su primer modelo.

### 3.2 Métricas

- **Técnicas:** WAPE y MAE de la venta esperada.
- **De negocio:** costo de la cantidad sugerida con `costos.csv`:
  `faltante · máx(real − sugerida, 0) + sobrante · máx(sugerida − real, 0)`.
  Es la métrica que decide el reemplazo del modelo.

### 3.3 Cantidad sugerida

Si faltar cuesta `cf` por unidad y sobrar cuesta `cs`, la cantidad que minimiza
el costo esperado es el cuantil `τ = cf / (cf + cs)` de la demanda (problema del
*newsvendor*). Con `costos.csv`, τ va de 0.29 en panadería (conviene pedir de
menos) a 0.95 en licores (conviene pedir de más).

**Método:** en un periodo que el modelo no vio (28 días de calibración) se mide
el error `log1p(real) − log1p(esperada)` de cada familia y se guarda su cuantil
τ. La sugerida es `expm1(log1p(esperada) + ajuste)`, redondeada a un entero no
negativo. Los ajustes se registran en MLflow con cada modelo.

**Alternativas:**
- *Sugerida = venta esperada:* costó 36 % más (237 315 contra 174 465 en la
  prueba), porque ignora que los costos son asimétricos.
- *Un LightGBM de cuantiles por cada τ distinto:* costó un poco más (178 818) y
  tardó siete veces más en entrenar.

---

## 4. Criterio de reemplazo del modelo vigente

### 4.1 El problema de la fuga de información

La forma habitual de comparar un modelo nuevo (retador) con el vigente
(campeón) es evaluar los dos en los datos más recientes. Pero si el vigente se
entrenó con parte de esos días, ya los conoce. LightGBM se ajusta mucho a sus
datos de entrenamiento, así que en la práctica el candidato casi nunca ganaría,
el modelo no se actualizaría y el servicio fallaría ante cambios de demanda.

### 4.2 El criterio

1. **Ventana de evaluación:** los últimos días (hasta 14) con predicciones
   registradas del vigente y ventas reales conocidas.
2. **El vigente se evalúa con las cantidades que realmente entregó** en esos
   días. Se calcularon antes de conocer esas ventas, así que no hay fuga.
3. **El candidato se entrena con datos anteriores a la ventana**, se calibra con
   los 28 días previos y predice la ventana con la misma información que tenía
   el servicio: ventas hasta el día anterior y la promoción de cada solicitud.
   Entrenamiento, calibración y evaluación nunca se superponen.
4. **Se promueve si su costo es al menos 2 % menor.** Si gana, se vuelve a
   entrenar con todos los datos antes de registrarlo, para no desperdiciar los
   días más recientes. Los ajustes de la cantidad sugerida se recalculan con un
   modelo auxiliar entrenado sin los últimos 28 días.
5. **Con menos de 7 días de evidencia, el vigente se mantiene.**

Si el entrenamiento falla o el candidato no supera el criterio, no se registra
ninguna versión y el alias no se mueve: el vigente no se ve afectado.

**Consecuencia:** justo después de una promoción, el nuevo vigente necesita al
menos 7 días de operación antes de poder ser reemplazado. Funciona como periodo
de prueba y evita cambiar de modelo por el ruido de pocos días.

**El 2 % de mejora mínima** evita reemplazar el modelo por diferencias que
pueden deberse al azar en una ventana corta.

**Primer modelo:** al levantar el producto desde cero no hay contra quién
compararse, así que se registra como vigente directamente, junto con su
comparación contra el baseline como evidencia (`novamercado.inicializar`). Si ya
existe un vigente, no se entrena de nuevo.

**Si MLflow no responde,** la inicialización espera y reintenta; nunca confunde
"no hay conexión" con "no hay modelo".

**Alternativas descartadas:**
- *Evaluar los dos modelos en los últimos días:* fuga a favor del vigente
  (sección 4.1).
- *Promover siempre el modelo más reciente:* no protege contra un
  reentrenamiento peor que el vigente, lo que el enunciado prohíbe.

### 4.3 Registro en MLflow

- Cada reentrenamiento queda como una corrida del experimento `novamercado`, con
  sus parámetros, métricas, motivo y la comparación por fila.
- Solo los modelos promovidos se registran como versión de
  `novamercado-ventas`, con el alias `vigente`, la corrida que la produjo y el
  motivo de la promoción. Así se puede rastrear cada versión hasta sus datos y
  parámetros.

---

## 5. Servicio y persistencia

### 5.1 La API solo traduce HTTP

Los endpoints leen el cuerpo como JSON libre y llaman a `servicio.py`. No se
declara un modelo de Pydantic en la firma del endpoint, porque FastAPI
rechazaría con 422 cualquier dato defectuoso antes de que la política del
producto pueda repararlo o advertirlo. Pydantic valida después de la limpieza,
en modo estricto, y también valida cada respuesta antes de enviarla.

### 5.2 Qué se registra

| Tabla | Contenido |
|---|---|
| `solicitudes` | Cada llamada, con su cuerpo original, el estado (`ok`, `corregido`, `advertencia`, `rechazada`, `error`), el motivo de rechazo y la versión del modelo |
| `correcciones` | Cada observación de calidad (campo, acción y detalle) |
| `predicciones` | Por familia: promoción usada, venta esperada, cantidad sugerida y versión del modelo |
| `observaciones` | La venta real vigente por fecha, tienda y familia, y si es atípica |
| `observaciones_historial` | Cada alta o cambio de una observación |
| `reentrenamientos` | Cada ejecución del DAG: estado, si se promovió, versión y motivo |

Las solicitudes rechazadas también se registran: sirven para medir qué
problemas llegan y con qué frecuencia.

### 5.3 Observaciones idempotentes

La llave primaria de `observaciones` es (tienda, fecha, familia). Al recibir un
envío, se compara cada valor con el guardado: si es igual no se escribe nada;
si es nuevo o distinto se inserta o actualiza y se anota en el historial.
`registros_guardados` cuenta solo esos cambios, así que reenviar una
observación idéntica responde 0. Todo ocurre en una transacción; si dos envíos
idénticos llegan a la vez, el segundo choca con la llave primaria y se
reintenta una vez, ya sin cambios.

**Alternativa:** guardar cada envío como una fila nueva y deduplicar al leer. Se
descartó porque complica todas las consultas y el contrato pide que el reenvío
no duplique información.

### 5.4 Varias solicitudes de la misma fecha

Una tienda puede pedir el pronóstico de una fecha más de una vez. Todas se
registran. Para comparar modelos y para tomar la promoción de un día se usa la
última solicitud de cada fecha, tienda y familia.

### 5.5 Modelo en memoria y recarga sin reinicio

El servicio predice con el modelo que tiene en memoria. Un hilo revisa cada 15
segundos la base de datos, MLflow y Airflow. Si el alias `vigente` apunta a
otra versión, la descarga y la usa en la siguiente solicitud. Un modelo
promovido se empieza a usar, en el peor caso, unos 15 segundos después de que
el DAG mueve el alias, muy por debajo del límite de 2 minutos.

**Alternativas:** que el DAG avise a la API con una llamada HTTP. Se descartó
porque, si esa llamada se pierde, el servicio queda con el modelo viejo; la
revisión periódica se corrige sola.

### 5.6 Si una dependencia falla

| Falla | Comportamiento |
|---|---|
| MLflow | Se sigue prediciendo con el modelo en memoria; `/health` responde `degradado` en la siguiente revisión (máximo 15 s) y vuelve a `ok` cuando MLflow responde |
| MLflow al arrancar | Se usa la copia local del último modelo descargado (volumen de Docker) |
| Airflow | `POST /admin/reentrenar` responde 503; `/health`, `degradado` |
| Base de datos | Las predicciones se responden igual, con solo el histórico como historia, y se registra el error; las observaciones responden 503 porque no se pueden guardar |
| Sin modelo | `/health` y los pronósticos responden 503 |

La prioridad es que la tienda reciba su pronóstico: perder el registro de una
predicción es menos grave que dejar a la tienda sin inventario planificado.

### 5.7 Estado de un reentrenamiento

`POST /admin/reentrenar` crea un registro `en_curso` y dispara el DAG en Airflow
con ese mismo identificador. Al terminar, el DAG escribe en la base de datos si
promovió, la versión vigente y el motivo. Si el DAG falla antes de escribir su
resultado, `GET /admin/reentrenar/{id}` lo detecta al consultar Airflow y
responde `fallido`, con la versión vigente sin cambios.

---

## 6. Contenedores y operación

| Servicio | Imagen | Persistencia |
|---|---|---|
| `db` | `postgres:16.9` | volumen `db-data` (bases `novamercado` y `mlflow`) |
| `mlflow` | propia, `python:3.12.11-slim-bookworm` + MLflow 3.18.0 | metadatos en `db`, artefactos en el volumen `mlflow-artifacts` |
| `inicializador` | propia (la misma de la API) | — |
| `api` | propia, `python:3.12.11-slim-bookworm` | copia local del modelo en el volumen `modelo-cache` |
| `airflow-*` | propia, `apache/airflow:3.2.2` | base en `airflow-db` (contenedor aparte), registros en `airflow-logs` |

**Versiones fijas.** Todas las imágenes base y las dependencias de Python tienen
versión exacta.

**Datos y credenciales fuera de las imágenes.** Los archivos publicados se montan
en solo lectura desde `datos/publicados/`. Las claves vienen de `.env`, que no
está en el repositorio; `.env.example` sirve de plantilla. Si falta `.env`,
`docker compose` se detiene con un mensaje que lo indica.

**MLflow en el PostgreSQL del producto, pero en otra base.** El enunciado exige
separar la base del producto de la de Airflow. MLflow usa una base aparte
(`mlflow`) dentro del mismo servidor del producto, para no levantar un tercer
PostgreSQL. *Alternativa:* SQLite en un volumen; se descartó porque MLflow
corre con varios procesos y SQLite no maneja bien la escritura concurrente.

**Primer modelo sin intervención.** El servicio `inicializador` corre
`novamercado.inicializar` y termina. Si ya hay un modelo con el alias
`vigente`, no hace nada. La API no espera a que termine: arranca, responde 503
en `/health` mientras no haya modelo y lo carga en la siguiente revisión (15
segundos). En las pruebas, entrenar y registrar el primer modelo tardó unos 40
segundos.

**Airflow con un entorno virtual aparte.** Las tareas del DAG ejecutan el código
del producto con `/opt/airflow/novamercado-venv`, no con el Python de Airflow.
Así las versiones de pandas, SQLAlchemy o MLflow que usa el producto no chocan
con las que Airflow necesita. *Alternativa:* instalar todo en el entorno de
Airflow; se descartó porque Airflow fija versiones de SQLAlchemy incompatibles
con las del producto.

**`LocalExecutor` en Airflow**, sin Celery ni Redis: el único DAG ejecuta pocas
tareas en secuencia.

**MLflow con lista de hosts permitidos.** MLflow 3 rechaza peticiones con un
encabezado `Host` desconocido (protección contra *DNS rebinding*). Se permiten
`mlflow` (el nombre del servicio dentro de Docker) y `localhost`.

**Fallas rápidas de MLflow.** La API usa un tiempo de espera de 5 segundos y sin
reintentos al consultar MLflow, para que una caída no bloquee la revisión
periódica.

**Prueba de operación.** Fuera de Docker, con PostgreSQL 16 y un servidor de
MLflow reales: al apagar MLflow, `/health` pasó a `degradado` en la siguiente
revisión y los pronósticos siguieron respondiendo; la API, reiniciada con MLflow
caído, arrancó en 3 segundos con la copia local del modelo; al volver MLflow,
`/health` lo reflejó en 8 segundos.
