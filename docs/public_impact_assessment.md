# Evaluación de Impacto Público, Ética y Mitigación de Sesgos

## 1. Impacto esperado

### Beneficiarios directos
| Audiencia | Cómo les impacta TEYVA |
|---|---|
| **Operarios DAGRD** | Dashboard único con estado de 21 comunas, alertas automáticas 7 días antes, eliminación de la necesidad de consultar 4 sistemas separados |
| **Comunidades en ladera** | Acceso en lenguaje natural al estado de riesgo de su barrio, canal directo para reportar señales de alerta |
| **Tomadores de decisión** | Vista consolidada para priorizar recursos de respuesta y prevención |
| **Equipos técnicos** | API REST consumible por otros sistemas institucionales |

### Escala del impacto potencial
- **Población en zona de riesgo:** aprox. 300,000 habitantes en comunas de ladera de Medellín.
- **Reducción de tiempo de respuesta:** de horas (detección reactiva) a días (predicción anticipada).
- **Escalabilidad:** la arquitectura soporta extensión a los 10 municipios del Área Metropolitana sin cambios de fondo.

### Valor público
- Reducción de pérdidas humanas y materiales por deslizamientos.
- Optimización de la asignación de recursos de gestión del riesgo.
- Fortalecimiento de la gobernanza de datos abiertos en gestión territorial.

---

## 2. Evaluación ética

### 2.1 Autonomía y decisión humana
TEYVA es un sistema de **apoyo a la decisión**, no de decisión autónoma. Toda alerta requiere validación humana antes de activar protocolos de evacuación. El sistema no emite órdenes de evacuación directamente.

### 2.2 Transparencia algorítmica
- Las predicciones van acompañadas de explicaciones en lenguaje natural (qué factores las generaron).
- El modelo, sus métricas y los umbrales de clasificación son públicos en este repositorio.
- Los reportes ciudadanos quedan en estado `pending_review` hasta que un operario los verifica — no se propagan automáticamente al modelo.

### 2.3 Privacidad
- Los reportes ciudadanos no capturan datos de identificación personal.
- El `session_id` del chat es un UUID aleatorio, sin vinculación a identidad del usuario.
- Los logs de auditoría almacenan el hash SHA-256 del payload, no el payload completo.

### 2.4 Acceso equitativo
- La plataforma es web-first y no requiere instalación de app.
- El agente conversacional está diseñado para responder en lenguaje no técnico.
- Las alertas Slack van dirigidas a operarios institucionales; se planifica integración con canales comunitarios (WhatsApp, SMS) en versiones futuras.

---

## 3. Identificación y mitigación de sesgos

### 3.1 Sesgo de subregistro histórico
**Riesgo:** Las comunas con menor cobertura histórica de DAGRD pueden tener menos eventos registrados, lo que el modelo puede interpretar como "menor riesgo real".

**Mitigación:**
- Se incorporaron variables geotécnicas independientes de los registros históricos (pendiente, tipo de suelo).
- Se realiza análisis de distribución de eventos por comuna antes de cada reentrenamiento.
- Los eventos sintéticos (Snake Line) no se incluyen en el entrenamiento pero sirven para identificar zonas sin registro histórico pero con alta vulnerabilidad geotécnica.

### 3.2 Sesgo temporal (estacionalidad)
**Riesgo:** El modelo puede sobreajustarse a los patrones de lluvia de temporadas específicas presentes en el dataset de entrenamiento.

**Mitigación:**
- Validación temporal pasado→futuro (`train_auc_temporal`) que evalúa el modelo en datos cronológicamente posteriores al entrenamiento.
- Benchmark fijo congelado para detectar degradación del modelo en producción.

### 3.3 Sesgo de resolución espacial
**Riesgo:** Las predicciones a nivel de comuna pueden enmascarar diferencias de riesgo dentro de la misma unidad territorial.

**Mitigación:**
- Los niveles de alerta se acompañan de recomendaciones específicas para zonas de ladera.
- El agente puede filtrar eventos por barrio cuando DAGRD los registra con esa granularidad.
- Se planifica aumentar la resolución a nivel de cuadrante (ver `alembic/versions/b3c4d5e6f7a8_mesh_quadrants.py`).

### 3.4 Sesgo de acceso tecnológico
**Riesgo:** Las comunidades más vulnerables pueden tener menor acceso a la plataforma web.

**Mitigación:**
- Diseño responsive para dispositivos móviles de gama baja.
- Planificación de integración con canales de mensajería accesibles (WhatsApp Business API).

---

## 4. Riesgos residuales

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Falsa alarma masiva que cause pánico | Baja | Alto | Alertas solo a operarios DAGRD, no a ciudadanía directamente en esta versión |
| Fallo de datos SIATA durante emergencia | Media | Alto | Fallback a últimos valores conocidos + alerta Slack de scraper caído |
| Uso del sistema sin validación institucional | Media | Medio | Documentación clara de que las rutas de evacuación son candidatas, no instrucciones oficiales |
| Degradación silenciosa del modelo | Baja | Medio | Benchmark fijo + `metrics.json` con `trained_at` y `git_commit_sha` para trazabilidad |
