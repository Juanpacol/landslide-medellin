# Requirements Document

## Introduction

Medellín enfrenta un riesgo persistente de deslizamientos de tierra, especialmente en las comunas nororiental y noroccidental, donde la topografía de ladera, la densidad poblacional y los patrones de precipitación intensa crean condiciones de alta vulnerabilidad. Actualmente no existe una herramienta integrada que correlacione eventos históricos de emergencias, datos de precipitación y características topográficas para identificar patrones de riesgo y generar alertas tempranas.

Este sistema de análisis y visualización de riesgo de deslizamientos integra tres fuentes de datos públicas — registros históricos de emergencias del Cuerpo Oficial de Bomberos de Medellín, datos de precipitación diaria del IDEAM/SIATA, y cartografía de comunas y topografía de GeoMedellín/IGAC — para producir un dashboard interactivo con mapas de riesgo, correlaciones estadísticas y alertas basadas en umbrales de precipitación.

## Glossary

- **Sistema**: El sistema de análisis y visualización de riesgo de deslizamientos de Medellín.
- **Dashboard**: Interfaz web interactiva que presenta mapas, gráficas y alertas de riesgo.
- **Ingesta**: Proceso de descarga, validación y almacenamiento de datos desde fuentes externas.
- **Pipeline**: Secuencia automatizada de pasos de procesamiento de datos.
- **Evento_Deslizamiento**: Registro de emergencia cuyo campo `tipo_emergencia` contiene 'desliz' o 'movimiento'.
- **Registro_Precipitacion**: Medición diaria de precipitación en milímetros asociada a una estación meteorológica en Medellín (cod_municipio=05001).
- **Capa_Topografica**: Geometría GeoJSON de comunas de Medellín enriquecida con pendiente promedio del IGAC.
- **Indice_Riesgo**: Valor numérico calculado por comuna que combina frecuencia histórica de deslizamientos, precipitación acumulada y pendiente promedio.
- **Umbral_Precipitacion**: Valor en milímetros de precipitación diaria o acumulada que activa una alerta de riesgo.
- **Correlacion**: Medida estadística (coeficiente de Pearson o Spearman) entre precipitación y frecuencia de deslizamientos por período y zona.
- **Zona_Ladera**: Área geográfica con pendiente promedio superior a 15 grados, predominante en comunas nororiental y noroccidental.
- **API_Emergencias**: Endpoint de datos abiertos de MeData que provee registros CSV de emergencias atendidas por el Cuerpo Oficial de Bomberos.
- **API_Precipitacion**: Endpoint de datos.gov.co o portal de descarga de SIATA que provee registros CSV de precipitación diaria.
- **Procesador**: Componente del Sistema responsable de transformar, filtrar y enriquecer los datos crudos.
- **Visualizador**: Componente del Dashboard responsable de renderizar mapas y gráficas.
- **Alertador**: Componente del Sistema responsable de evaluar umbrales y emitir alertas.

## Requirements

### Requirement 1: Ingesta de datos de emergencias históricas

**User Story:** Como analista de riesgo, quiero cargar y filtrar los registros históricos de emergencias del Cuerpo Oficial de Bomberos, para que pueda trabajar únicamente con eventos de deslizamiento o movimiento de tierra.

#### Acceptance Criteria

1. WHEN el Pipeline ejecuta la ingesta de emergencias, THE Ingesta SHALL descargar el archivo CSV desde `https://medata.gov.co/dataset/emergencias-atendidas-cuerpo-oficial-bomberos`.
2. WHEN el archivo CSV de emergencias es descargado, THE Procesador SHALL filtrar únicamente los registros donde `tipo_emergencia` contenga 'desliz' o 'movimiento' (comparación sin distinción de mayúsculas).
3. WHEN el Procesador filtra los registros, THE Procesador SHALL retener los campos `fecha`, `tipo_emergencia`, `comuna`, `barrio`, `latitud` y `longitud` para cada Evento_Deslizamiento.
4. IF un registro de emergencia no contiene valor en los campos `latitud` o `longitud`, THEN THE Procesador SHALL marcar el registro como incompleto y excluirlo del análisis espacial, pero incluirlo en el análisis temporal por comuna.
5. IF la descarga del CSV de emergencias falla, THEN THE Ingesta SHALL registrar el error con código de falla y timestamp, y continuar el Pipeline con los datos previamente almacenados.
6. THE Procesador SHALL normalizar el campo `fecha` al formato ISO 8601 (YYYY-MM-DD) para todos los Evento_Deslizamiento.

---

### Requirement 2: Ingesta de datos de precipitación

**User Story:** Como analista de riesgo, quiero cargar los registros históricos de precipitación diaria de estaciones en Medellín, para que pueda correlacionarlos con los eventos de deslizamiento.

#### Acceptance Criteria

1. WHEN el Pipeline ejecuta la ingesta de precipitación, THE Ingesta SHALL intentar descargar datos desde `https://www.datos.gov.co/dataset/precipitacion-diaria-colombia` filtrando por `cod_municipio=05001`.
2. IF la descarga desde datos.gov.co no retorna registros para Medellín, THEN THE Ingesta SHALL utilizar el archivo CSV histórico descargado del portal SIATA (2018–2024) como fuente alternativa.
3. WHEN el archivo CSV de precipitación es procesado, THE Procesador SHALL retener los campos `fecha`, `estacion`, `precipitacion_mm` y `cod_municipio` para cada Registro_Precipitacion.
4. WHEN el Procesador carga los Registro_Precipitacion, THE Procesador SHALL normalizar el campo `fecha` al formato ISO 8601 (YYYY-MM-DD).
5. IF un Registro_Precipitacion contiene un valor negativo o no numérico en `precipitacion_mm`, THEN THE Procesador SHALL descartar ese registro y registrar la anomalía en el log de calidad de datos.
6. THE Procesador SHALL calcular la precipitación acumulada de 3 días y 7 días anteriores para cada Registro_Precipitacion, almacenando los valores como `precipitacion_acum_3d` y `precipitacion_acum_7d`.

---

### Requirement 3: Ingesta de datos geoespaciales

**User Story:** Como analista de riesgo, quiero cargar la cartografía de comunas y los datos de pendiente topográfica de Medellín, para que pueda asociar cada evento de deslizamiento a su contexto geográfico.

#### Acceptance Criteria

1. WHEN el Pipeline ejecuta la ingesta geoespacial, THE Ingesta SHALL descargar el GeoJSON de comunas desde `https://geomedellin-m-medellin.opendata.arcgis.com/`.
2. WHEN el GeoJSON de comunas es descargado, THE Procesador SHALL validar que cada feature contenga los campos `commune_id`, `nombre_comuna` y `geometry` de tipo Polygon o MultiPolygon.
3. IF un feature del GeoJSON no contiene `commune_id` o `geometry` válida, THEN THE Procesador SHALL omitir ese feature y registrar la advertencia en el log de calidad de datos.
4. WHERE los datos de pendiente del IGAC estén disponibles, THE Procesador SHALL enriquecer cada feature de comuna con el campo `pendiente_promedio` en grados, construyendo la Capa_Topografica.
5. WHERE los datos de pendiente del IGAC no estén disponibles, THE Procesador SHALL asignar `pendiente_promedio = null` y marcar la comuna como sin dato topográfico.
6. THE Procesador SHALL clasificar cada comuna como Zona_Ladera cuando `pendiente_promedio` sea mayor o igual a 15 grados.

---

### Requirement 4: Correlación estadística entre precipitación y deslizamientos

**User Story:** Como analista de riesgo, quiero calcular la correlación entre precipitación y frecuencia de deslizamientos por comuna y período, para que pueda identificar patrones que expliquen el riesgo.

#### Acceptance Criteria

1. THE Procesador SHALL calcular el coeficiente de correlación de Spearman entre `precipitacion_mm` diaria y la frecuencia diaria de Evento_Deslizamiento para cada comuna con al menos 10 eventos históricos registrados.
2. THE Procesador SHALL calcular el coeficiente de correlación de Spearman entre `precipitacion_acum_3d` y la frecuencia de Evento_Deslizamiento para cada comuna con al menos 10 eventos históricos registrados.
3. THE Procesador SHALL calcular el coeficiente de correlación de Spearman entre `precipitacion_acum_7d` y la frecuencia de Evento_Deslizamiento para cada comuna con al menos 10 eventos históricos registrados.
4. WHEN el Procesador calcula correlaciones, THE Procesador SHALL producir para cada comuna un objeto con los campos `commune_id`, `correlacion_diaria`, `correlacion_3d`, `correlacion_7d` y `n_eventos`.
5. IF una comuna tiene menos de 10 Evento_Deslizamiento registrados, THEN THE Procesador SHALL asignar `correlacion_diaria = null`, `correlacion_3d = null` y `correlacion_7d = null` para esa comuna, e incluir una nota de insuficiencia de datos.

---

### Requirement 5: Cálculo del Índice de Riesgo por comuna

**User Story:** Como analista de riesgo, quiero obtener un índice de riesgo consolidado por comuna, para que pueda priorizar las zonas que requieren atención o monitoreo.

#### Acceptance Criteria

1. THE Procesador SHALL calcular el Indice_Riesgo para cada comuna combinando: frecuencia histórica normalizada de Evento_Deslizamiento (peso 0.4), precipitación acumulada de 7 días normalizada (peso 0.4) y pendiente promedio normalizada (peso 0.2).
2. WHEN el Procesador calcula el Indice_Riesgo, THE Procesador SHALL normalizar cada componente al rango [0, 1] usando min-max scaling sobre el conjunto de comunas con datos completos.
3. THE Procesador SHALL clasificar el Indice_Riesgo en cuatro categorías: Bajo (0.0–0.25), Medio (0.25–0.50), Alto (0.50–0.75) y Crítico (0.75–1.0).
4. IF una comuna no tiene dato de `pendiente_promedio`, THEN THE Procesador SHALL calcular el Indice_Riesgo usando únicamente los componentes de frecuencia (peso 0.5) y precipitación (peso 0.5), e indicar que el índice es parcial.
5. THE Procesador SHALL recalcular el Indice_Riesgo cada vez que se actualicen los datos de precipitación o emergencias.

---

### Requirement 6: Visualización del mapa de riesgo

**User Story:** Como usuario del dashboard, quiero ver un mapa interactivo de Medellín con las comunas coloreadas según su nivel de riesgo, para que pueda identificar visualmente las zonas más vulnerables.

#### Acceptance Criteria

1. THE Visualizador SHALL renderizar un mapa coroplético de Medellín donde cada comuna esté coloreada según la categoría de su Indice_Riesgo: verde (Bajo), amarillo (Medio), naranja (Alto) y rojo (Crítico).
2. WHEN el usuario hace clic en una comuna del mapa, THE Visualizador SHALL mostrar un panel lateral con: nombre de la comuna, Indice_Riesgo, número de Evento_Deslizamiento históricos, precipitación acumulada de 7 días y clasificación de Zona_Ladera.
3. THE Visualizador SHALL superponer en el mapa los puntos de Evento_Deslizamiento con coordenadas válidas como marcadores individuales.
4. WHEN el usuario selecciona un rango de fechas en el Dashboard, THE Visualizador SHALL actualizar el mapa para mostrar únicamente los Evento_Deslizamiento ocurridos en ese rango.
5. THE Visualizador SHALL renderizar el mapa en menos de 3 segundos después de que los datos estén disponibles en el Dashboard.
6. WHERE el dispositivo del usuario soporte pantallas táctiles, THE Visualizador SHALL permitir zoom y desplazamiento del mapa mediante gestos táctiles.

---

### Requirement 7: Visualización de series de tiempo y correlaciones

**User Story:** Como analista de riesgo, quiero ver gráficas de series de tiempo que comparen precipitación y frecuencia de deslizamientos, para que pueda analizar la relación temporal entre ambas variables.

#### Acceptance Criteria

1. THE Visualizador SHALL renderizar una gráfica de doble eje Y que muestre simultáneamente la precipitación diaria (mm) y la frecuencia diaria de Evento_Deslizamiento para el período seleccionado.
2. WHEN el usuario selecciona una comuna específica en el Dashboard, THE Visualizador SHALL filtrar la gráfica de series de tiempo para mostrar únicamente los datos de esa comuna.
3. THE Visualizador SHALL mostrar los coeficientes de correlación de Spearman (`correlacion_diaria`, `correlacion_3d`, `correlacion_7d`) calculados para la comuna seleccionada en un panel de métricas.
4. THE Visualizador SHALL renderizar una gráfica de dispersión entre `precipitacion_acum_3d` y frecuencia de Evento_Deslizamiento para la comuna seleccionada, con la línea de tendencia superpuesta.
5. IF la comuna seleccionada tiene `correlacion_diaria = null` por insuficiencia de datos, THEN THE Visualizador SHALL mostrar el mensaje "Datos insuficientes para calcular correlación (mínimo 10 eventos requeridos)" en el panel de métricas.

---

### Requirement 8: Sistema de alertas por umbral de precipitación

**User Story:** Como operador de emergencias, quiero recibir alertas cuando la precipitación supere umbrales críticos en zonas de ladera, para que pueda activar protocolos de prevención oportunamente.

#### Acceptance Criteria

1. THE Alertador SHALL evaluar el Umbral_Precipitacion cada vez que se actualicen los Registro_Precipitacion.
2. WHEN `precipitacion_mm` diaria supera 50 mm en una estación asociada a una Zona_Ladera, THE Alertador SHALL generar una alerta de nivel Naranja para la comuna correspondiente.
3. WHEN `precipitacion_acum_3d` supera 100 mm en una estación asociada a una Zona_Ladera, THE Alertador SHALL generar una alerta de nivel Rojo para la comuna correspondiente.
4. WHEN el Alertador genera una alerta, THE Dashboard SHALL mostrar la alerta en un banner visible en la parte superior de la interfaz con: nivel de alerta, nombre de la comuna, valor de precipitación que activó la alerta y timestamp.
5. IF el Alertador genera múltiples alertas simultáneas para distintas comunas, THEN THE Dashboard SHALL mostrar todas las alertas activas en una lista ordenada por nivel de severidad (Rojo primero).
6. WHEN una alerta es generada, THE Alertador SHALL registrar la alerta en el historial de alertas con: `commune_id`, `nivel`, `precipitacion_valor`, `tipo_umbral` y `timestamp`.

---

### Requirement 9: Exportación y acceso a datos procesados

**User Story:** Como investigador, quiero exportar los datos procesados y el índice de riesgo calculado, para que pueda utilizarlos en análisis externos o reportes.

#### Acceptance Criteria

1. THE Dashboard SHALL proveer un botón de exportación que genere un archivo CSV con los campos: `commune_id`, `nombre_comuna`, `indice_riesgo`, `categoria_riesgo`, `n_eventos`, `correlacion_3d`, `precipitacion_acum_7d` y `pendiente_promedio`.
2. THE Dashboard SHALL proveer un botón de exportación que genere un archivo GeoJSON con la Capa_Topografica enriquecida con el Indice_Riesgo y la categoría de riesgo por comuna.
3. WHEN el usuario solicita una exportación, THE Dashboard SHALL generar el archivo en menos de 5 segundos y ofrecerlo para descarga directa en el navegador.
4. THE Sistema SHALL exponer un endpoint REST `GET /api/risk-index` que retorne el Indice_Riesgo actual por comuna en formato JSON.
5. THE Sistema SHALL exponer un endpoint REST `GET /api/events` que acepte parámetros de filtro `commune_id`, `fecha_inicio` y `fecha_fin`, y retorne los Evento_Deslizamiento correspondientes en formato JSON.

---

### Requirement 10: Calidad de datos y trazabilidad

**User Story:** Como analista de datos, quiero conocer el estado de calidad de los datos ingeridos y procesados, para que pueda confiar en los resultados del análisis y detectar problemas en las fuentes.

#### Acceptance Criteria

1. THE Sistema SHALL mantener un log de calidad de datos que registre: fuente de datos, fecha de ingesta, número de registros descargados, número de registros válidos, número de registros descartados y motivo de descarte.
2. THE Dashboard SHALL mostrar un panel de estado de datos con: fecha de última actualización de cada fuente, porcentaje de registros válidos por fuente y estado de conexión (OK / Error) para cada API.
3. IF el porcentaje de registros válidos de cualquier fuente cae por debajo del 70%, THEN THE Sistema SHALL mostrar una advertencia en el panel de estado de datos indicando la fuente afectada y el porcentaje actual.
4. THE Sistema SHALL conservar los archivos CSV crudos descargados de cada fuente durante al menos 30 días para permitir reprocesamiento.
5. FOR ALL Evento_Deslizamiento procesados, THE Procesador SHALL mantener trazabilidad del registro original en el CSV fuente mediante el campo `source_row_id`.

---

### Requirement 11: Rendimiento y disponibilidad

**User Story:** Como usuario del dashboard, quiero que el sistema responda de forma fluida y esté disponible durante el hackathon, para que pueda demostrar la solución sin interrupciones.

#### Acceptance Criteria

1. THE Dashboard SHALL cargar la vista inicial con el mapa y los datos más recientes en menos de 5 segundos en una conexión de red estándar (10 Mbps).
2. THE Sistema SHALL completar el Pipeline completo de ingesta y procesamiento de las tres fuentes de datos en menos de 10 minutos.
3. WHEN el usuario interactúa con filtros de fecha o selección de comuna, THE Dashboard SHALL actualizar las visualizaciones en menos de 2 segundos.
4. THE Sistema SHALL soportar al menos 10 usuarios concurrentes sin degradación de rendimiento superior al 20% en los tiempos de respuesta.
5. IF el Pipeline falla en algún paso, THEN THE Sistema SHALL continuar sirviendo los datos del último procesamiento exitoso y mostrar la fecha de los datos en el Dashboard.
