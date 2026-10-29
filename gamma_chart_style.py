"""A single clean dark NET GAMMA chart style for NDX, GLD and USO.

Visualization-only: never recalculates, normalizes or replaces Cboe Gamma.
The common price and gamma axes are supplied by each market's existing engine.
"""
import math
import plotly.graph_objects as go

COLORS = {
    "background": "#0b111d",
    "plot": "#101a2a",
    "text": "#e8eef7",
    "muted": "#91a4bc",
    "grid": "rgba(148, 163, 184, 0.14)",
    "green": "#34d399",
    "red": "#fb7185",
    "guide": "#fbbf24",
}


def top_levels(rows, level_field, value_field, shift=0.0):
    """Raw max-positive / max-negative strikes and total NET in native Gamma units."""
    eligible = []
    for row in rows:
        try:
            level = float(row[level_field]) + shift
            value = float(row[value_field])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isfinite(level) and math.isfinite(value):
            eligible.append((level, value))
    if not eligible:
        return {"positive": None, "negative": None, "total": None}
    positives = [r for r in eligible if r[1] > 0]
    negatives = [r for r in eligible if r[1] < 0]
    return {
        "positive": max(positives, key=lambda v: v[1]) if positives else None,
        "negative": min(negatives, key=lambda v: v[1]) if negatives else None,
        "total": sum(x[1] for x in eligible),
    }


def profile_chart(rows, symbol, reference, common_x, shared_y, *,
                  level_field="strike", gamma_field="net",
                  price_shift=0.0, ndx=False, show_close=True):
    """Build market-neutral horizontal Gamma bars with identical axis conventions."""
    if not rows:
        raise ValueError("Profilo senza strike.")
    levels = [float(r[level_field]) + price_shift for r in rows]
    values = [float(r[gamma_field]) for r in rows]
    if not all(math.isfinite(x) for x in levels + values):
        raise ValueError("Gamma/strike non finito.")
    gaps = [b - a for a, b in zip(levels, levels[1:]) if b > a]
    bar_height = min(0.78 * min(gaps), 4.0) if gaps else 0.75
    custom = []
    for r in rows:
        if ndx:
            custom.append([r["strike_index"], r["call_gamma"], r["put_gamma"]])
        else:
            custom.append([r["call"], r["put"], r["call_gamma"], r["put_gamma"],
                           r["call_oi"], r["put_oi"], r["call_volume"], r["put_volume"]])
    template = (
        "Livello future/indice %{y:,.2f}<br>Strike indice %{customdata[0]:,.2f}"
        "<br>NET %{x:+.4f}<br>Call ponderata %{customdata[1]:.4f}"
        "<br>Put ponderata %{customdata[2]:.4f}<extra></extra>"
    ) if ndx else (
        f"Strike {symbol} %{{y:,.2f}}<br>NET %{{x:+.4f}}"
        "<br>Call ponderata %{customdata[0]:.4f}"
        "<br>Put ponderata %{customdata[1]:.4f}"
        "<br>Gamma Call %{customdata[2]:.6f}<br>Gamma Put %{customdata[3]:.6f}"
        "<br>OI Call %{customdata[4]:,.0f} · OI Put %{customdata[5]:,.0f}"
        "<br>Volume Call %{customdata[6]:,.0f} · Volume Put %{customdata[7]:,.0f}"
        "<extra></extra>"
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=values, y=levels, orientation="h", width=bar_height,
        marker=dict(color=[COLORS["green"] if n >= 0 else COLORS["red"] for n in values],
                    line=dict(width=0)),
        customdata=custom, hovertemplate=template,
        name="NET GAMMA",
    ))
    fig.add_vline(x=0, line_width=1.4, line_color=COLORS["muted"])
    if show_close:
        fig.add_hline(y=reference + price_shift, line_dash="dash", line_width=1.5,
                      line_color=COLORS["guide"])
    fig.update_layout(
        height=620, margin=dict(l=12, r=18, t=18, b=24),
        paper_bgcolor=COLORS["background"], plot_bgcolor=COLORS["plot"],
        font=dict(family="Arial, sans-serif", color=COLORS["text"], size=12),
        bargap=0.08, showlegend=False, hovermode="closest",
        hoverlabel=dict(bgcolor="#19263a", font_color=COLORS["text"]),
        xaxis=dict(title="NET GAMMA · (OI + Volume) × Gamma",
                   range=common_x, showgrid=True, gridcolor=COLORS["grid"],
                   zeroline=False, fixedrange=False, tickformat="~s"),
        yaxis=dict(title=(f"Prezzo {'NQ' if price_shift else 'NDX'}" if ndx else
                          f"Strike {symbol} (USD)"),
                   range=shared_y, autorange=False, showgrid=True,
                   gridcolor=COLORS["grid"], tickformat=",.2f"),
    )
    return fig
