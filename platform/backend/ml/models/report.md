# Reporte de evaluación TEYVA ML

## Métricas de entrenamiento (CV / artefactos)

- Muestras: **8429**
- Positivos (evento en +7d): **26**
- Mejor modelo: **XGBClassifier**
- AUC-ROC medio (CV): **0.9435**
- Estrategia CV: **5-fold**
- AUC-ROC en dataset completo (ajustado): **0.9443**

## Métricas en dataset completo (umbral 0.5)

- AUC-ROC: **0.8891**
- F1: **0.0204**
- Precisión: **0.0103**
- Recall: **0.8077**
- Exactitud: **0.7606**

_Nota: al evaluar sobre el mismo conjunto usado para ajustar el modelo, estas métricas son optimistas; la referencia principal de generalización es el AUC-ROC de CV en `metrics.json`._
