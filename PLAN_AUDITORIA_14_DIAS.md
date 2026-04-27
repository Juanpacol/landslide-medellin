# Plan de Corrección Integral (14 Días)

Este documento organiza la auditoría en un plan diario ejecutable para cerrar riesgos de **ML**, **agente conversacional**, **scraper**, **API** y **operación**.

## Objetivo general

Pasar de un estado MVP a una base confiable para producción:

- Reducir riesgo de seguridad y exposición de datos.
- Mejorar calidad de datos y frescura de ingesta.
- Corregir sesgos/errores metodológicos de ML.
- Reducir alucinaciones del agente con respuestas verificables.
- Aumentar trazabilidad, observabilidad y capacidad de operación.

## Supuestos y alcance

- Se trabaja sobre el repositorio actual (`backend` + `static`).
- Se pueden crear migraciones Alembic y cambios de contrato API.
- Se prioriza impacto/seguridad sobre features nuevas.
- Cada día incluye entregables verificables.

## Convención de prioridades

- **P0**: crítico (seguridad, integridad, datos).
- **P1**: alto impacto funcional.
- **P2**: madurez operativa/calidad.

---

## Día 1 — Cerrar superficie de ataque (P0)

### Qué se hace

- Restringir CORS por ambiente (dev/staging/prod), eliminando `allow_origins=["*"]`.
- Proteger endpoints de acción (`/risk/predict-all`, rutas scraper sensibles) con autenticación mínima.
- Añadir rate limiting básico en `/chat`.
- Definir variables de entorno de seguridad faltantes.

### Por qué

- Con CORS abierto y endpoints de ejecución sin auth, cualquier origen puede invocar operaciones costosas o leer información sensible.
- El primer bloqueo debe ser perimetral para evitar abuso mientras se corrigen capas internas.

### Entregables

- Middleware CORS parametrizado por `ENV`.
- Dependencia de auth aplicada a endpoints críticos.
- Límite por IP/sesión en chat.
- Documento corto de configuración por ambiente.

### Criterios de aceptación

- Un dominio no permitido recibe error CORS.
- Llamar a endpoint crítico sin credenciales devuelve `401/403`.
- Exceso de requests al chat devuelve `429`.

### Riesgos y mitigación

- Riesgo: romper frontend local.
- Mitigación: incluir `localhost` explícitamente en entorno dev.

---

## Día 2 — Seguridad de sesiones y ownership (P0)

### Qué se hace

- Asociar `session_id` con `user_id` (o actor) en conversación.
- Validar ownership en `GET /chat/history/{session_id}`.
- Normalizar formato de `session_id` y rechazar IDs inválidos.
- Definir política de retención (TTL) inicial.

### Por qué

- Sin ownership, un cliente puede consultar historial de otra sesión.
- El historial de chat suele contener datos sensibles y contexto operativo.

### Entregables

- Modelo/consulta con ownership.
- Validación de acceso por sesión.
- Regla de retención documentada.

### Criterios de aceptación

- Usuario A no puede leer sesión de usuario B.
- Sesiones inválidas no pasan validación.

### Riesgos y mitigación

- Riesgo: migración de conversaciones existentes.
- Mitigación: script de backfill con owner por defecto temporal.

---

## Día 3 — Memoria del agente sin duplicados (P0)

### Qué se hace

- Elegir una sola capa para persistir turnos (API o `agent/chat.py`).
- Eliminar guardado duplicado de `user` y `assistant`.
- Añadir idempotencia de turno (`turn_id`) para reintentos.
- Crear tests de no-duplicación.

### Por qué

- Duplicar mensajes contamina contexto, empeora respuestas y eleva costo.
- Historial limpio mejora trazabilidad y debugging.

### Entregables

- Flujo de persistencia único.
- Test unitario/integración de 1 request = 2 mensajes máximos.

### Criterios de aceptación

- Una llamada de chat no crea filas duplicadas.
- Historial mantiene orden y cardinalidad esperada.

### Riesgos y mitigación

- Riesgo: dependencia implícita del frontend en duplicados.
- Mitigación: validar contrato de respuesta y ajustar cliente si aplica.

---

## Día 4 — Geocodificación robusta en scraper (P0)

### Qué se hace

- Corregir `geocode_events.py`: si hay coordenadas pero falla lookup, intentar fallback por texto (`tipo_emergencia`).
- Registrar método de resolución (`coords`, `text`, `none`) por evento.
- Mejorar resumen final de ejecución.

### Por qué

- Hoy se pierden eventos geocodificables cuando falla la ruta por coordenadas.
- Mayor tasa de `commune_id` nulo afecta ML, alertas y chat.

### Entregables

- Lógica de fallback completa.
- Métricas de resolución por método.

### Criterios de aceptación

- Disminuye el número de eventos con `commune_id` nulo en corrida de prueba.
- El log reporta distribución por método.

### Riesgos y mitigación

- Riesgo: asignaciones por texto con baja precisión.
- Mitigación: etiquetar confianza y revisar reglas de texto.

---

## Día 5 — Idempotencia real en base de datos (P0)

### Qué se hace

- Crear migración Alembic con constraints/índices únicos:
  - `landslide_events.source_row_id` (cuando exista).
  - llave lógica de features por `commune_id + reference_date + source`.
- Reemplazar inserciones por `upsert` (`ON CONFLICT`).
- Ajustar scrapers para aprovechar upsert.

### Por qué

- La deduplicación solo en código no resiste concurrencia ni retries simultáneos.
- Idempotencia en BD es la única garantía fuerte.

### Entregables

- Migración aplicada en entorno de prueba.
- Inserciones idempotentes en rutas críticas.

### Criterios de aceptación

- Re-ejecutar el mismo lote no incrementa registros duplicados.
- Concurrencia básica no produce colisiones silenciosas.

### Riesgos y mitigación

- Riesgo: conflicto con datos históricos inconsistentes.
- Mitigación: limpieza previa y migración con reporte de colisiones.

---

## Día 6 — Normalización canónica de comunas (P0)

### Qué se hace

- Definir lista canónica única de IDs (`1..16,50,60,70,80,90`) en módulo compartido.
- Corregir `predict_all_comunas` para iterar IDs canónicos.
- Alinear scraper/API/ML a la misma fuente de verdad.

### Por qué

- IDs mezclados causan huecos de cobertura y errores de join.
- El sistema actual puede dejar corregimientos sin predicción.

### Entregables

- Módulo común de comunas.
- Predict batch cubriendo 21 territorios reales definidos.

### Criterios de aceptación

- Se generan predicciones para todos los IDs canónicos.
- API y frontend muestran cobertura completa.

### Riesgos y mitigación

- Riesgo: inconsistencias de datos legados.
- Mitigación: tabla de mapeo temporal y script de normalización.

---

## Día 7 — Contrato único de categorías de riesgo (P1)

### Qué se hace

- Definir taxonomía única (ejemplo: `bajo`, `medio`, `alto`, `critico`).
- Actualizar:
  - categorización en `ml/predict.py`,
  - filtros de alertas en `api/routes/risk.py`,
  - consumo frontend (`static/lib/api.ts` y componentes).
- Centralizar umbrales en constantes compartidas.

### Por qué

- Inconsistencias de mayúsculas/tildes rompen alertas y reportes.
- Un contrato único evita bugs silenciosos entre capas.

### Entregables

- Enum/constantes comunes.
- Alertas funcionando con categorías reales persistidas.

### Criterios de aceptación

- Al menos una predicción alta/critica aparece en `/risk/alerts`.
- No hay conversiones ad hoc de strings dispersas.

### Riesgos y mitigación

- Riesgo: ruptura visual en frontend.
- Mitigación: capa de compatibilidad temporal para etiquetas viejas.

---

## Día 8 — Corregir leakage de entrenamiento ML (P0)

### Qué se hace

- Mover `SMOTE` y escalado dentro de un `Pipeline` evaluado por CV.
- Dejar de aplicar `SMOTE.fit_resample` antes del split.
- Corregir bug de `cv_name` no inicializado en caso monoclase.

### Por qué

- Evaluar sobre datos sintetizados antes del split sobreestima AUC y degrada decisiones reales.
- Bug de monoclase puede romper ejecución en escenarios extremos.

### Entregables

- Nuevo pipeline de entrenamiento.
- Manejo explícito de casos sin clase positiva/negativa.

### Criterios de aceptación

- Entrenamiento corre sin leakage detectado por revisión de flujo.
- Métricas reportadas provienen de CV correcto.

### Riesgos y mitigación

- Riesgo: “caída” aparente de métricas.
- Mitigación: comunicar que refleja desempeño real, no regresión funcional.

---

## Día 9 — Validación temporal y por grupos (P0)

### Qué se hace

- Implementar evaluación temporal (walk-forward o bloque temporal).
- Evitar mezclar ventanas de tiempo que filtren futuro al pasado.
- Medir desempeño por comuna o macro-zona.

### Por qué

- El problema es temporal; CV aleatorio no simula producción.
- La generalización real requiere respetar orden temporal.

### Entregables

- Estrategia de split temporal documentada.
- Reporte de métricas por ventana temporal.

### Criterios de aceptación

- Ningún fold usa información de fechas futuras para predecir pasadas.
- Reporte separa performance global y por segmento.

### Riesgos y mitigación

- Riesgo: menor tamaño efectivo por fold.
- Mitigación: ajustar horizonte y granularidad temporal.

---

## Día 10 — Métricas de negocio para clase rara (P1)

### Qué se hace

- Incluir PR-AUC, precision/recall por umbral, `recall@k`.
- Definir umbral operativo por costo (falsos negativos vs falsos positivos).
- Actualizar `metrics.json` y reporte para nueva métrica primaria.

### Por qué

- AUC-ROC sola es engañosa en datasets muy desbalanceados.
- Operación de riesgo requiere priorizar sensibilidad controlada.

### Entregables

- Curva PR y tabla de trade-offs por umbral.
- Umbral oficial versionado.

### Criterios de aceptación

- Existe decisión explícita de umbral con justificación.
- Reporte incluye métrica primaria y secundaria.

### Riesgos y mitigación

- Riesgo: desacuerdo de negocio sobre sensibilidad.
- Mitigación: presentar 2-3 escenarios con impacto estimado.

---

## Día 11 — Calibración y versionado robusto ML (P1)

### Qué se hace

- Calibrar probabilidades (`Platt` o isotónica según data).
- Guardar metadata de entrenamiento: dataset hash, rango temporal, librerías, semilla.
- Versionar modelo automáticamente (`fecha + git_sha + hash`).

### Por qué

- Score sin calibración puede no representar probabilidad real.
- Sin trazabilidad completa no se puede auditar ni reproducir.

### Entregables

- Artefacto con metadata extendida.
- `model_version` no hardcoded.

### Criterios de aceptación

- Se puede reconstruir exactamente de dónde salió un modelo.
- `risk_score` calibrado con evidencia cuantitativa.

### Riesgos y mitigación

- Riesgo: complejidad adicional de despliegue.
- Mitigación: script único de empaquetado de artefactos.

---

## Día 12 — Anti-alucinación del agente (P0/P1)

### Qué se hace

- Reestructurar respuesta del agente en 3 fases:
  - `retrieve`: datos estructurados desde BD.
  - `generate`: respuesta natural limitada a evidencia.
  - `verify`: rechazo/reescritura de claims no soportados.
- Definir formato interno de evidencia (`fuente`, `fecha`, `confianza`, `faltantes`).
- Política explícita de incertidumbre (“No confirmado con datos recientes”).

### Por qué

- Contexto inyectado no garantiza veracidad final.
- Sin verificación factual, el modelo puede alucinar con tono convincente.

### Entregables

- Pipeline de respuesta verificable.
- Disminución de claims no soportados en pruebas manuales.

### Criterios de aceptación

- Ante falta de datos, el agente no inventa valores/fechas.
- Cada respuesta relevante conserva trazabilidad de evidencia interna.

### Riesgos y mitigación

- Riesgo: respuestas más conservadoras.
- Mitigación: optimizar estilo sin perder precisión factual.

---

## Día 13 — Observabilidad y SRE mínimo (P2)

### Qué se hace

- Introducir `run_id` transversal (scraper -> ML -> API -> chat).
- Estandarizar logs estructurados con campos clave.
- Métricas de frescura:
  - última corrida OK por fuente,
  - latencia,
  - lag de datos.
- Alertas técnicas básicas (fallo jobs, latencia alta, ausencia de datos).

### Por qué

- Sin observabilidad no hay operación confiable ni diagnóstico rápido.
- La auditoría debe convertirse en monitoreo continuo.

### Entregables

- Dashboard/consulta mínima de salud operativa.
- Guía de troubleshooting inicial.

### Criterios de aceptación

- Se detecta automáticamente una fuente caída o atrasada.
- Se puede trazar una predicción hasta su corrida origen.

### Riesgos y mitigación

- Riesgo: ruido de alertas iniciales.
- Mitigación: ajustar umbrales en la primera semana.

---

## Día 14 — Hardening, QA final y salida controlada (P1/P2)

### Qué se hace

- Ejecutar suite mínima:
  - tests API críticos,
  - smoke test scraper,
  - entrenamiento/predicción smoke ML,
  - pruebas de chat anti-alucinación.
- Checklist final de seguridad y consistencia de contratos.
- Plan de rollback y ventana de deploy.
- Cierre con reporte de estado antes/después.

### Por qué

- Sin validación final, mejoras puntuales pueden introducir regresiones.
- Se necesita evidencia de cierre para operar con confianza.

### Entregables

- Informe final con:
  - riesgos cerrados,
  - riesgos residuales,
  - backlog de siguiente iteración.

### Criterios de aceptación

- Todos los P0 cerrados.
- P1 en estado estable o con plan calendarizado.
- Despliegue exitoso sin incidentes críticos 24h.

### Riesgos y mitigación

- Riesgo: deuda remanente en frontend o scripts legados.
- Mitigación: abrir fase 2 de consolidación arquitectónica.

---

## Definición de “hecho” por día

Un día se considera completo si cumple:

- Código o configuración implementada.
- Prueba mínima ejecutada y documentada.
- Evidencia de resultado (logs, endpoint, reporte o métrica).
- Riesgo residual anotado.

## Métricas globales de éxito (fin de 14 días)

- **Seguridad**: 0 endpoints críticos abiertos sin auth.
- **Datos**: duplicados controlados por constraints + upserts.
- **Cobertura**: 100% IDs canónicos con predicción.
- **ML**: validación temporal sin leakage y métrica primaria definida.
- **Agente**: reducción de respuestas no verificables.
- **Operación**: frescura de fuentes y trazabilidad por `run_id`.

## Backlog inmediato post-14 días

- Refactor para eliminar backend legacy duplicado.
- Separación de dependencias por perfil (`api`, `ml`, `scraper`).
- Suite de pruebas automatizadas más amplia.
- Monitoreo de drift en producción y reentrenamiento gobernado.

