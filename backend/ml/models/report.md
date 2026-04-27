# Reporte de evaluación TEYVA ML

## Métricas de entrenamiento (CV / artefactos)

- Muestras: **8429**
- Positivos (evento en +7d): **26**
- Mejor modelo: **XGBClassifier**
- AUC-ROC medio (CV): **0.7653**
- Estrategia CV: **5-fold**
- AUC-ROC en dataset completo (ajustado): **0.8966**

## Métricas en dataset completo (umbral 0.5)

- AUC-ROC: **0.8966**
- F1: **0.0000**
- Precisión: **0.0000**
- Recall: **0.0000**
- Exactitud: **0.9969**

_Nota: al evaluar sobre el mismo conjunto usado para ajustar el modelo, estas métricas son optimistas; la referencia principal de generalización es el AUC-ROC de CV en `metrics.json`._
