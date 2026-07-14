# Serverless — Funciones Lambda para Reportes Automatizados

Este directorio contiene las configuraciones para desplegar funciones serverless
que generan reportes automáticos sin necesidad de un servidor siempre activo.

## Casos de uso

- **Reporte diario de situación:** Genera y envía por Slack el estado de riesgo de todas las comunas cada mañana.
- **Alerta de umbral:** Se dispara cuando el score de riesgo de cualquier comuna supera 0.65 (alto).
- **Reporte semanal PDF:** Exporta el notebook `05_reportes_automaticos.ipynb` como PDF y lo adjunta a Slack.

## Estructura sugerida

```
serverless/
├── report_daily/
│   ├── handler.py      # Punto de entrada Lambda
│   └── serverless.yml  # Configuración Serverless Framework
├── alert_trigger/
│   ├── handler.py
│   └── serverless.yml
└── weekly_report/
    ├── handler.py
    └── serverless.yml
```

## Despliegue (AWS Lambda con Serverless Framework)

```bash
npm install -g serverless
cd deployments/serverless/report_daily
serverless deploy --stage prod
```

## Nota

En el MVP actual, estas funciones se reemplazan por los cron jobs de GitHub Actions
(`.github/workflows/`), que tienen la misma funcionalidad sin costo adicional.
Las configuraciones Serverless se proveen para el caso en que el proyecto migre
a infraestructura propia o requiera mayor control del escalado.
