# Reporte de evaluación TEYVA ML

## Métricas de entrenamiento (CV / artefactos)

- Muestras: **6459**
- Positivos (evento en +7d): **901**
- Mejor modelo: **RandomForestClassifier**
- AUC-ROC medio (CV): **0.6316**
- Estrategia CV: **5-fold**
- AUC-ROC en dataset completo (ajustado): **0.6482**

## Métricas en dataset completo (umbral 0.5)

- AUC-ROC: **0.6263**
- F1: **0.2828**
- Precisión: **0.1678**
- Recall: **0.9001**
- Exactitud: **0.3632**

_Nota: al evaluar sobre el mismo conjunto usado para ajustar el modelo, estas métricas son optimistas; la referencia principal de generalización es el AUC-ROC de CV en `metrics.json`._
