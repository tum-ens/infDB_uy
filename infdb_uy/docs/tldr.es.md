# InfDB Uruguay – resumen

*Octubre de 2026 · [English](tldr.md) · [Deutsch](tldr.de.md) · Español · Inicio: `docker compose up --build`, luego <http://localhost:8050>.*

## Objetivo y estado

**Objetivo.** Aplicar el pipeline InfDB a Uruguay, comenzando por **Cordón**, un barrio de 228 ha de Montevideo.

**Hecho:**

- inventario de los datos abiertos de Uruguay y su correspondencia con las entradas de InfDB
- un pipeline que descarga y prepara los datos de Cordón sin supuestos de modelación
- un explorador web de esos datos

**Pendiente:** la adaptación de InfDB propiamente dicha (edificios a partir de LiDAR, asignación de atributos, distribución de la población).

## En qué difiere Uruguay de las entradas alemanas de InfDB

| Entrada de InfDB (Alemania) | Uruguay | Valoración |
|---|---|---|
| Edificios LoD2 en CityGML | **No hay geometría de edificios abierta.** Montevideo tiene un relevamiento LiDAR 2024 abierto (clasificado, clase 6 construcciones). En el resto: Google Open Buildings 2.5D, modelos de superficie IDE 2017–18, OSM. | Principal carencia. Hay que derivar huellas y alturas. |
| Año de construcción, pisos y superficie estimados a partir de la grilla del censo y la geometría | **Observados en el catastro.** La DNC publica cada mes, para todo el país, cada *línea de construcción*: nivel, destino, categoría, estado, cubierta, m², año y año remanente de partes reformadas. | Mejor. Los pasos SQL 05 y 09 de InfDB pasan a ser consultas en lugar de estimaciones. |
| Grilla de 100 m del censo alemán | Censo 2023 por zona censal (13.648 polígonos, solo Montevideo) o segmento (todo el país). Microdatos ponderados con fuente de calefacción, aire acondicionado y colector solar por segmento, tras aceptar los términos del INE. | Polígonos en lugar de grilla. Variables energéticas que InfDB no tiene. |
| Límites administrativos BKG / AGS | Códigos del INE y de la DNC, que difieren (`01`/`01020` vs. `V`/`AA`); hace falta una tabla de correspondencia. | Adaptar |
| Calles de basemap.de, códigos postales | Ejes de calles de la Intendencia y números de puerta con padrón y tramo de calle, es decir, una asignación edificio→calle lista para usar. No se necesitan códigos postales. | Equivalente en Montevideo |
| Tipología TABULA | No existe. Construirla a partir de categoría DNC × cubierta × año, más los materiales del censo. | Carencia |
| Parámetros de red para pylovo | No hay datos de UTE | Carencia |
| SRC 3035 | EPSG:32721 (UTM 21S) en todas partes. El LiDAR usa EPSG:5382 (SIRGAS-ROU98). | Configuración |

**En pocas palabras:** Uruguay tiene mejores *atributos* de edificios que Alemania, pero no tiene *geometría* de edificios. Los pasos de estimación de InfDB se reducen y hay que agregar un paso de derivación de edificios a partir del LiDAR. Detalles (en inglés): [comparación](infdb-comparison.md), [cambios necesarios](required-changes.md).

## Piloto Cordón: resultados verificados

**Volúmenes de datos:**

- 5.130 padrones y 27.802 unidades catastrales
- 147.823 líneas de construcción
- 287 zonas censales que tocan el barrio (186 totalmente dentro, 35.591 habitantes)
- 8 hojas LiDAR (164 millones de puntos, 1,2 GB)

**Datos masivos del catastro vs. cédulas catastrales oficiales (PDF).** Comparados con 100 cédulas obtenidas del servicio web de Catastro:

- 99 coinciden exactamente, en cada línea, superficie, año, categoría, estado, valor y en el histórico de 4 años.
- La única diferencia (V-AA-137) es una reforma de 2015 que figura en la cédula, generada en el momento, pero no en el extracto masivo de septiembre.
- Por lo tanto, no hace falta extraer datos de los PDF.

**Uniones.** El 99,9 % de los padrones de Montevideo tiene polígono. En Cordón, las claves de padrones y de números de puerta coinciden salvo en 8 padrones.

**Reproducibilidad.** Un `docker compose up --build` desde cero descarga todo (≈ 1,5 GB) y levanta el panel en unos 9 minutos. Los archivos originales quedan registrados con SHA-256 en un manifiesto.

## Hallazgos que requieren una decisión antes de modelar

1. **Líneas de dos regímenes en un mismo padrón.** 917 padrones tienen líneas tanto en régimen común (CO) como en propiedad horizontal (PH), típicamente durante una conversión. 40.512 líneas (1,1 millones de m², 23 % de la superficie) pertenecen a un régimen sin registro de unidad. Sumar todas las líneas cuenta esos edificios dos veces.
2. **Tres «superficies construidas» no coinciden.** Todas las líneas dan 4,79 millones de m², las líneas de regímenes existentes 3,68 millones de m² y el área edificada de las propias unidades 3,07 millones de m². Las líneas incluyen también muros, palieres y áreas abiertas. ¿Qué definición alimenta el `floor_area` de InfDB?
3. **Calidad de datos.** 581 líneas tienen año 0, 22.301 tienen 0 m² y 16.460 son «a construir» (aún no construidas). Algunos códigos no tienen etiqueta en la tabla de la DNC (p. ej. el código de cubierta 5 en 6.252 líneas).
4. **LiDAR.** Las hojas están en EPSG:5382 y contienen clases (11, 13, 15, 24, 105, 120, 121) que la Intendencia no documenta.
5. **Zonas censales** que cruzan el límite del barrio suman 18.471 habitantes más. Cómo atribuirlos es una decisión de modelación.

Todo esto se informa, se marca y se puede filtrar en el panel, pero **no se resuelve**. Según la regla del pipeline, los datos originales se mantienen sin cambios.

## Próximos pasos (propuesta)

1. Derivar huellas y alturas de edificios a partir del LiDAR (MDT, MDS normalizado, huellas divididas por padrón).
2. Definir reglas para los hallazgos 1, 2 y 5; luego adaptar los pasos SQL 00, 02 y 05–13 de InfDB con un selector de país.
3. Aceptar los términos de ANDA del INE (microdatos censales ponderados). El pipeline de ingesta está listo y probado con archivos de ejemplo.
4. Esbozar una tipología uruguaya de edificios para ro-heat. Consultar a UTE por datos de red para pylovo.
5. Extender de Cordón a barrios con viviendas unifamiliares (Carrasco) y asentamientos irregulares (Casavalle), y luego a todo Montevideo.
