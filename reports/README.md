# Reportes y Resultados — TEYVA

## Estructura

```
reports/
├── figures/
│   ├── distribuciones.png     # Distribución de variables clave
│   ├── correlaciones.png      # Mapa de correlaciones entre features
│   └── matriz_confusion.png   # Matriz de confusión del modelo en validación
└── reporte_final.pdf          # Reporte técnico completo exportado
```

## Generar las figuras

Las figuras se generan automáticamente al ejecutar los notebooks:

```bash
# Distribuciones y correlaciones
jupyter nbconvert --to notebook --execute notebooks/03_analisis_descriptivo.ipynb

# Matriz de confusión
jupyter nbconvert --to notebook --execute notebooks/04_modelo_predictivo.ipynb
```

Las imágenes se guardan en `reports/figures/`.

## reporte_final.pdf

Exportado desde `notebooks/05_reportes_automaticos.ipynb`. Contiene:
- Resumen ejecutivo del estado de riesgo
- Métricas del modelo
- Análisis por comuna
- Tendencias de precipitación
