"""
Cuándo dos reportes sísmicos son el MISMO sismo. Lógica pura, sin I/O.

## El problema

`seismic_events` guarda reportes, no sismos. Un único sismo físico produce:

- K filas de SIATA — una por cada estación de la red que lo registró;
- una fila de USGS, con su propia solución de tiempo y epicentro;
- una fila del SGC, con otra.

La deduplicación anterior era por `(event_local_at.isoformat(), epicenter_label)`.
Eso solo funciona dentro de SIATA, donde todas las filas de un sismo comparten
tiempo y etiqueta calculados idénticos. Entre agencias **no colapsa ni un solo
duplicado**: los tiempos de origen difieren en segundos y las etiquetas son
textos distintos ("12 km NE of Betulia, Colombia" vs el municipio del SGC vs
"Sismo en Medellín - Antioquia").

Y como `ml/seismic_features.py` calcula una **Σ de magnitud²**, cada sismo
contaría 2-3 veces y la señal se inflaría de forma cuadrática, en silencio. Por
eso esto es un prerrequisito de integrar USGS/SGC, no un pulido posterior.

## Por qué las tolerancias son estas

No son números redondos elegidos al azar:

- **±120 s.** Las soluciones de tiempo de ORIGEN entre agencias concuerdan en
  segundos. El margen es por SIATA, cuyo `fecha_local` por estación es un
  timestamp de disparo/llegada: para un sismo regional a 200-400 km, la onda S
  llega decenas de segundos después del origen. 120 s cubre eso y sigue muy por
  debajo del espaciado real entre sismos sentidos en Colombia.
- **60 km.** Las soluciones de epicentro entre agencias difieren de rutina 10-40
  km, por distinta geometría de estaciones y distinto modelo de velocidades.
  60 km captura eso sin fusionar dos sismos distintos en fallas diferentes.
- **|ΔM| ≤ 1.0.** Las agencias reportan escalas distintas (ML, Mw, Mb) que
  difieren 0.3-0.7 habitualmente. 1.0 es la cota honesta. Es una **guarda contra
  fusiones absurdas**, no el discriminante principal.
- **±45 s cuando falta lat/lon.** Sin geometría se aprieta el tiempo en vez de
  fusionar con una ventana laxa.

## Precedencia SGC > USGS > SIATA

Para los valores CANÓNICOS del sismo. El SGC es la autoridad sismológica
nacional, así que tiene las mejores soluciones locales; USGS es de calidad global
y rápido, pero sus epicentros en Colombia son más gruesos; SIATA es una red local
densa, insustituible para detectar sismos pequeños que las otras dos no ven, pero
su "epicentro" publicado por estación es el menos autoritativo. Esos sismos
locales forman clústeres de una sola fuente, que es exactamente lo correcto.

La magnitud de consenso es **la del ganador de precedencia**, no el máximo ni la
media: el máximo sesga al alza (y la feature eleva al cuadrado, amplificándolo) y
la media mezcla escalas incompatibles. Así queda trazable vía `canonical_source`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.geo import distance_km

MATCH_TIME_WINDOW_S = 120.0
MATCH_DISTANCE_KM = 60.0
MATCH_MAGNITUDE_DELTA = 1.0
MATCH_TIME_ONLY_WINDOW_S = 45.0

# Índice 0 = máxima autoridad. Una fuente desconocida queda por debajo de todas.
SOURCE_PRECEDENCE: tuple[str, ...] = ("sgc", "usgs", "siata_sismos")


@dataclass(frozen=True)
class EventKey:
    """Lo mínimo para decidir si dos reportes son el mismo sismo.

    Deliberadamente NO es un modelo de SQLAlchemy: así estas reglas se pueden
    testear sin base de datos, que es la parte que se va a retocar con el tiempo.
    """

    event_at: datetime
    source: str
    magnitude: float | None = None
    depth_km: float | None = None
    lat: float | None = None
    lon: float | None = None
    label: str | None = None

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None


def source_rank(source: str | None) -> int:
    """Posición en la precedencia; más bajo gana. Fuente desconocida va al final."""
    if not source:
        return len(SOURCE_PRECEDENCE)
    try:
        return SOURCE_PRECEDENCE.index(source)
    except ValueError:
        return len(SOURCE_PRECEDENCE)


def seconds_apart(a: EventKey, b: EventKey) -> float:
    return abs((a.event_at - b.event_at).total_seconds())


def km_apart(a: EventKey, b: EventKey) -> float | None:
    """Distancia entre epicentros, o None si a alguno le faltan coordenadas."""
    if not (a.has_coords and b.has_coords):
        return None
    # Keyword-only a propósito: `haversine_km` es lon-primero y invertirlo
    # devuelve una distancia equivocada pero plausible.
    return distance_km(lat1=a.lat, lon1=a.lon, lat2=b.lat, lon2=b.lon)  # type: ignore[arg-type]


def events_match(a: EventKey, b: EventKey) -> bool:
    """¿Son `a` y `b` reportes del mismo sismo físico?"""
    # La magnitud solo DESCARTA; nunca confirma por sí sola.
    if a.magnitude is not None and b.magnitude is not None:
        if abs(a.magnitude - b.magnitude) > MATCH_MAGNITUDE_DELTA:
            return False

    dt = seconds_apart(a, b)
    d_km = km_apart(a, b)
    if d_km is None:
        # Sin geometría en algún lado: se aprieta la ventana temporal.
        return dt <= MATCH_TIME_ONLY_WINDOW_S
    return dt <= MATCH_TIME_WINDOW_S and d_km <= MATCH_DISTANCE_KM


def pick_canonical(current: EventKey, candidate: EventKey) -> EventKey:
    """Cuál de los dos aporta los valores canónicos del clúster.

    Gana la fuente de mayor precedencia. A igualdad de fuente se conserva
    `current`, para que reprocesar no cambie el resultado sin motivo.
    """
    return candidate if source_rank(candidate.source) < source_rank(current.source) else current


def best_match(candidate: EventKey, clusters: list[EventKey]) -> int | None:
    """Índice del clúster que mejor encaja con `candidate`, o None.

    Enlace simple contra el representante de cada clúster (no cierre transitivo
    sobre las filas crudas): así el agrupamiento no depende del orden de llegada.
    Si varios encajan, gana el más cercano en tiempo; el desempate final es el
    índice más bajo, para que sea determinista.
    """
    best_i: int | None = None
    best_dt = float("inf")
    for i, cluster in enumerate(clusters):
        if not events_match(candidate, cluster):
            continue
        dt = seconds_apart(candidate, cluster)
        if dt < best_dt:
            best_dt, best_i = dt, i
    return best_i


def merge_sources(existing: list[str], new_source: str) -> list[str]:
    """Lista de fuentes del clúster, sin duplicados y en orden de precedencia."""
    merged = set(existing) | {new_source}
    return sorted(merged, key=lambda s: (source_rank(s), s))
