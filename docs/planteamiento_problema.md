# Planteamiento del Problema

## 1. Contexto territorial

Medellín es una ciudad enclavada en un valle montañoso con pendientes pronunciadas. Aproximadamente el 40% de su territorio urbano se asienta sobre laderas con alto potencial de inestabilidad geotécnica. Las 21 comunas incluyen sectores donde la combinación de lluvia intensa, suelos arcillosos saturados y construcción informal en zonas de riesgo crea condiciones para deslizamientos de tierra que históricamente han causado pérdidas humanas y materiales significativas.

## 2. Problema identificado

La gestión del riesgo de deslizamientos en Medellín enfrenta tres brechas críticas:

### 2.1 Fragmentación de la información
Las fuentes de datos relevantes (SIATA, DAGRD, IDEAM, GeoMedellín) operan de forma independiente, sin integración en tiempo real. Un operario de la Gestión del Riesgo debe consultar múltiples plataformas para construir una imagen del estado actual, lo que introduce demora y posibilidad de error.

### 2.2 Ausencia de predicción anticipada
El sistema actual es reactivo: las alertas se emiten después de que el evento ocurre o cuando ya hay señales visibles de inestabilidad. No existe un modelo que integre las variables disponibles para estimar la probabilidad de deslizamiento por comuna en los próximos 7 días.

### 2.3 Barrera de acceso para la ciudadanía
Los datos técnicos (índices de riesgo, umbrales de lluvia, fichas geotécnicas) no están disponibles en un formato comprensible para los habitantes de las zonas de ladera, que son los más expuestos y los primeros en poder detectar señales tempranas (grietas, agua turbia, movimiento de tierra).

## 3. Necesidad pública

La Alcaldía de Medellín, a través del DAGRD (Departamento Administrativo de Gestión del Riesgo de Desastres), requiere un sistema que:

- Centralice los datos de riesgo en una sola plataforma operativa.
- Anticipe eventos con suficiente tiempo para activar protocolos preventivos.
- Comunique el riesgo en lenguaje claro, accionable y diferenciado por audiencia (operarios, comunidades, tomadores de decisión).

## 4. Objetivo general

Desarrollar una plataforma de inteligencia territorial que integre datos abiertos de múltiples fuentes institucionales, aplique modelos de aprendizaje automático para predecir el nivel de riesgo de deslizamiento por comuna a 7 días, y entregue esta información a través de un dashboard interactivo y un asistente conversacional con IA.

## 5. Objetivos específicos

1. Integrar en tiempo real las cuatro fuentes de datos abiertos principales: SIATA, DAGRD, IDEAM y GeoMedellín.
2. Entrenar un modelo clasificador de riesgo (bajo / medio / alto / crítico) optimizado para minimizar falsos negativos en un contexto de riesgo a la vida.
3. Desplegar una API REST consumible por sistemas institucionales de gestión del riesgo.
4. Construir un agente conversacional que responda preguntas en lenguaje natural sobre el estado de riesgo de cualquier comuna.
5. Implementar un canal de reporte ciudadano integrado en el sistema.

## 6. Alcance

- **Territorio:** 21 comunas urbanas de Medellín + corregimientos.
- **Horizonte de predicción:** 7 días.
- **Usuarios objetivo:** Operarios de DAGRD, equipos técnicos de gestión del riesgo, ciudadanía en zonas de ladera.
- **Fuera del alcance:** Predicción de inundaciones, municipios del Área Metropolitana (extensible en versiones futuras).

## 7. Pregunta de investigación

> ¿Es posible anticipar el nivel de riesgo de deslizamiento por comuna en Medellín con al menos 7 días de antelación, integrando datos abiertos de precipitación, eventos históricos y características geotécnicas del territorio, con suficiente sensibilidad para no omitir ningún evento real?
