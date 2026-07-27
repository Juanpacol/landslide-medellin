"""
Generación de gráficas PNG para alertas enriquecidas.

Cada alerta de TEYVA puede incluir una gráfica que muestra *por qué* se disparó:
el pico de lluvia de los últimos días contra el umbral configurado, más el nivel
de riesgo del modelo. Las gráficas se renderizan con matplotlib (backend Agg, sin
display) y se devuelven como bytes PNG en memoria.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")  # backend sin display (servidor)
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from db.models.rainfall_timeseries import RainfallTimeseries  # noqa: E402

logger = logging.getLogger(__name__)

# Paleta TEYVA (coherente con el dashboard)
_COLOR_BAR = "#5B8DEF"  # azul lluvia normal
_COLOR_PEAK = "#E5484D"  # rojo pico/sobre umbral
_COLOR_THRESHOLD = "#F5A623"  # naranja umbral
_COLOR_TEXT = "#2D2A26"
_COLOR_GRID = "#E6E1DA"


async def _daily_rainfall(
    commune_id: str, db: AsyncSession, days: int = 7
) -> list[tuple[datetime, float]]:
    """Suma diaria de lluvia de los últimos `days` días para una comuna."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date_trunc("day", RainfallTimeseries.snapshot_at)
    stmt = (
        select(day.label("d"), func.coalesce(func.sum(RainfallTimeseries.precip_mm), 0.0))
        .where(RainfallTimeseries.commune_id == commune_id)
        .where(RainfallTimeseries.snapshot_at >= cutoff)
        .group_by(day)
        .order_by(day)
    )
    rows = (await db.execute(stmt)).all()
    return [(r[0], float(r[1] or 0.0)) for r in rows]


def build_rainfall_alert_chart(
    daily: list[tuple[datetime, float]],
    threshold_mm: float,
    commune_name: str,
    risk_category: str | None = None,
    risk_score: float | None = None,
) -> bytes:
    """
    Construye una gráfica de barras de lluvia diaria con la línea de umbral.
    Las barras que superan el umbral se pintan en rojo (el pico que disparó la alerta).
    Devuelve PNG en bytes.
    """
    fig, ax = plt.subplots(figsize=(7.5, 3.6), dpi=130)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    if not daily:
        ax.text(
            0.5,
            0.5,
            "Sin datos de lluvia recientes",
            ha="center",
            va="center",
            fontsize=12,
            color=_COLOR_TEXT,
            transform=ax.transAxes,
        )
        ax.axis("off")
        return _fig_to_png(fig)

    dates = [d for d, _ in daily]
    values = [v for _, v in daily]
    colors = [_COLOR_PEAK if v >= threshold_mm else _COLOR_BAR for v in values]

    bars = ax.bar(dates, values, color=colors, width=0.6, zorder=3)

    # Línea de umbral
    ax.axhline(
        threshold_mm,
        color=_COLOR_THRESHOLD,
        linestyle="--",
        linewidth=1.6,
        zorder=2,
        label=f"Umbral {threshold_mm:.0f} mm",
    )

    # Etiquetas de valor sobre cada barra
    for bar, v in zip(bars, values):
        if v > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                v,
                f"{v:.0f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color=_COLOR_TEXT,
                zorder=4,
            )

    # Estilo
    ax.set_ylabel("Lluvia (mm)", fontsize=10, color=_COLOR_TEXT)
    title = f"Lluvia últimos {len(daily)} días — {commune_name}"
    if risk_category:
        score_txt = f" · Riesgo {risk_category.upper()}"
        if risk_score is not None:
            score_txt += f" ({risk_score:.0%})"
        title += score_txt
    ax.set_title(title, fontsize=11.5, color=_COLOR_TEXT, fontweight="bold", pad=10)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax.grid(axis="y", color=_COLOR_GRID, linewidth=0.8, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_COLOR_GRID)
    ax.tick_params(colors=_COLOR_TEXT, labelsize=9)
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)

    ax.set_ylim(0, max(max(values), threshold_mm) * 1.25 + 1)
    fig.tight_layout()
    return _fig_to_png(fig)


def build_risk_trend_chart(
    history: list[tuple[datetime, float]],
    commune_name: str,
) -> bytes:
    """Gráfica de línea con la evolución del score de riesgo en el tiempo."""
    fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=130)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    if not history:
        ax.text(
            0.5,
            0.5,
            "Sin histórico de riesgo",
            ha="center",
            va="center",
            fontsize=12,
            color=_COLOR_TEXT,
            transform=ax.transAxes,
        )
        ax.axis("off")
        return _fig_to_png(fig)

    dates = [d for d, _ in history]
    scores = [v for _, v in history]
    ax.plot(dates, scores, color=_COLOR_PEAK, linewidth=2.2, marker="o", markersize=4, zorder=3)
    ax.fill_between(dates, scores, color=_COLOR_PEAK, alpha=0.08, zorder=1)

    # Bandas de categoría
    ax.axhspan(0.90, 1.0, color="#E5484D", alpha=0.06)
    ax.axhspan(0.65, 0.90, color="#F5A623", alpha=0.06)

    ax.set_ylabel("Score de riesgo", fontsize=10, color=_COLOR_TEXT)
    ax.set_title(
        f"Evolución del riesgo — {commune_name}",
        fontsize=11.5,
        color=_COLOR_TEXT,
        fontweight="bold",
        pad=10,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(axis="y", color=_COLOR_GRID, linewidth=0.8, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(colors=_COLOR_TEXT, labelsize=9)
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    return _fig_to_png(fig)


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def ascii_sparkline(values: list[float]) -> str:
    """Mini sparkline ASCII para el texto del mensaje (fallback sin imagen)."""
    if not values:
        return "▁▁▁▁▁▁▁"
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    if hi == lo:
        return blocks[0] * len(values)
    out = []
    for v in values:
        idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
        out.append(blocks[idx])
    return "".join(out)


async def rainfall_chart_for_commune(
    commune_id: str,
    db: AsyncSession,
    threshold_mm: float,
    commune_name: str,
    risk_category: str | None = None,
    risk_score: float | None = None,
    days: int = 7,
) -> tuple[bytes, list[float]]:
    """Helper: consulta + grafica. Devuelve (png_bytes, valores_diarios)."""
    daily = await _daily_rainfall(commune_id, db, days=days)
    png = build_rainfall_alert_chart(daily, threshold_mm, commune_name, risk_category, risk_score)
    return png, [v for _, v in daily]
