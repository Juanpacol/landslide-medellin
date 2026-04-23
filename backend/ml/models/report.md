# Reporte de evaluación TEYVA ML

## Métricas de entrenamiento (CV / artefactos)

- Muestras: **25**
- Positivos (evento en +7d): **14**
- Mejor modelo: **RandomForestClassifier**
- AUC-ROC medio (CV): **0.6169**
- Estrategia CV: **LOO**
- AUC-ROC en dataset completo (ajustado): **1.0000**

## Métricas en dataset completo (umbral 0.5)

- AUC-ROC: **1.0000**
- F1: **1.0000**
- Precisión: **1.0000**
- Recall: **1.0000**
- Exactitud: **1.0000**

_Nota: al evaluar sobre el mismo conjunto usado para ajustar el modelo, estas métricas son optimistas; la referencia principal de generalización es el AUC-ROC de CV en `metrics.json`._
