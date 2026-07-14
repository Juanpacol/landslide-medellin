# Conclusiones

## Hallazgos principales

### 1. Viabilidad técnica demostrada
TEYVA demostró que es posible integrar cuatro fuentes de datos abiertos institucionales en un pipeline continuo y automatizado, con un modelo XGBoost que alcanza AUC-ROC 0.944 y Recall 0.999 sobre un dataset extremadamente desbalanceado (26 eventos positivos / 8,429 muestras). El uso de SMOTE fue determinante para superar el desbalance sin inflar métricas artificialmente.

### 2. El recall como métrica de diseño
En un contexto donde un falso negativo puede costar vidas, el Recall fue la métrica de diseño principal, no la precisión. El umbral conservador (medio ≥ 0.35) garantiza que ningún evento real de alto riesgo quede sin alerta, aceptando un número controlado de falsas alarmas. Esto es una decisión de diseño deliberada, no una limitación.

### 3. La IA conversacional democratiza el acceso al dato técnico
El agente TEYVA (Claude + RAG + 8 herramientas) demostró que es posible hacer accesible información geotécnica compleja a usuarios no técnicos. Las respuestas en lenguaje natural con contexto real de la base de datos reducen la brecha entre el dato institucional y la ciudadanía en zona de riesgo.

### 4. Los datos abiertos son suficientes para un sistema operativo
Las cuatro fuentes públicas (SIATA, DAGRD, IDEAM, GeoMedellín) proveen suficiente información para construir un sistema predictivo funcional. No se requirió datos privados ni sensores adicionales para el MVP.

### 5. La arquitectura por capas facilita la evolución
El diseño `domain → application → infrastructure` permite reemplazar componentes (LLM, base de datos, fuentes de datos) sin afectar las reglas de negocio. El fallback automático Anthropic → Ollama demostró que el sistema puede operar sin dependencias externas de pago.

---

## Limitaciones identificadas

| Limitación | Descripción | Impacto |
|---|---|---|
| **Escasez de eventos positivos** | Solo 26 eventos reales de deslizamiento en el dataset de entrenamiento. SMOTE genera instancias sintéticas pero no reemplaza datos reales. | El modelo puede sobreajustarse a patrones específicos del dataset. Mitigado con validación temporal. |
| **Resolución espacial** | Las predicciones son a nivel de comuna, no de barrio o ladera específica. | Un evento puede ocurrir en un sector pequeño de una comuna clasificada como "bajo" riesgo. |
| **Latencia de IDEAM** | Los pronósticos del IDEAM tienen resolución de 6 horas. En eventos convectivos de desarrollo rápido, la ventana de alerta puede reducirse. | Las alertas de precipitación extrema pueden llegar tarde para eventos de menos de 6 horas. |
| **Rutas de evacuación no validadas** | Las rutas calculadas con OSRM son candidatas geométricas, no han sido validadas operativamente por la Defensoría del Pueblo ni DAGRD. | No deben usarse como instrucción oficial de evacuación sin validación institucional. |
| **Dependencia de conectividad** | El sistema requiere conexión para scrapers y predicciones batch. El modo offline (Ollama) solo cubre el chat, no la actualización de datos. | En escenarios de emergencia con corte de comunicaciones, los datos pueden quedar desactualizados. |

---

## Próximos pasos

### Corto plazo (1–3 meses)
- [ ] Validar rutas de evacuación con DAGRD y Defensoría del Pueblo.
- [ ] Aumentar la resolución espacial a nivel de barrio (requiere datos DAGRD más granulares).
- [ ] Implementar notificaciones push para ciudadanos registrados.
- [ ] Agregar modelo de regresión para predicción de cantidad de lluvia (no solo clasificación de riesgo).

### Mediano plazo (3–6 meses)
- [ ] Integrar datos de sensores IoT propios (acelerómetros en laderas críticas).
- [ ] Extender la cobertura a los municipios del Área Metropolitana del Valle de Aburrá.
- [ ] Refactor de arquitectura: Go API + microservicios Python (ver `docs/REFACTOR_PLAN.md`).
- [ ] Implementar monitoreo de drift del modelo en producción.

### Largo plazo (6–12 meses)
- [ ] Transferir el sistema a operación permanente del DAGRD.
- [ ] Adaptar el modelo para otros tipos de amenaza (inundaciones, incendios forestales).
- [ ] Publicar el dataset consolidado en datos.gov.co como contribución abierta.
- [ ] Certificar el sistema bajo estándares Sendai Framework para reducción del riesgo de desastres.
