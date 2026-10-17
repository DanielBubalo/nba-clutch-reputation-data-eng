"""Hexbin shot charts: hexagon size shows shot volume, colour shows FG% against the league from that spot.

Coordinates are nba_api's, in tenths of a foot with the hoop at (0, 0) (see court.py).
"""

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

HEX_RADIUS = 13  # centre to corner, in tenths of a foot: hexagons about 2.3 ft across
PRIOR_SHOTS = (
    5  # small samples are pulled toward the league by this many "average" shots
)
MIN_SIZE = 0.3  # the smallest hexagon drawn, as a share of full size
DIFF_RANGE = 0.10  # colour scale runs from 10 points below the league to 10 above
COLOUR_STEPS = 11
GLOW_STEPS = 3  # the hottest colour steps pulse and get a halo
HALO_SIZE = 1.45  # a halo is this much bigger than its hexagon


def hex_index(x: pd.Series, y: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Which hexagon each shot falls in, as axial (q, r) coordinates of a pointy-top hex grid."""
    q = (math.sqrt(3) / 3 * x - y / 3) / HEX_RADIUS
    r = (2 / 3 * y) / HEX_RADIUS
    # Round to the nearest hexagon centre (the standard "cube rounding" trick).
    cx, cz = np.asarray(q), np.asarray(r)
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    fix_x = (dx > dy) & (dx > dz)
    fix_z = ~fix_x & (dz >= dy)
    rx = np.where(fix_x, -ry - rz, rx)
    rz = np.where(fix_z, -rx - ry, rz)
    return rx.astype(int), rz.astype(int)


def hex_centre(q: np.ndarray, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return HEX_RADIUS * math.sqrt(3) * (q + r / 2), HEX_RADIUS * 1.5 * r


def hex_counts(shots: pd.DataFrame) -> pd.DataFrame:
    """Attempts and makes per hexagon."""
    q, r = hex_index(shots["loc_x"], shots["loc_y"])
    return (
        pd.DataFrame({"q": q, "r": r, "made": shots["shot_made_flag"].to_numpy()})
        .groupby(["q", "r"])["made"]
        .agg(attempts="size", makes="sum")
        .reset_index()
    )


def hex_stats(selected: pd.DataFrame, league: pd.DataFrame) -> pd.DataFrame:
    """One row per hexagon the selection shot from: volume, FG%, the league's FG% there, and the difference."""
    league_hexes = hex_counts(league)
    league_hexes["league_fg"] = league_hexes["makes"] / league_hexes["attempts"]
    stats = hex_counts(selected).merge(
        league_hexes[["q", "r", "league_fg"]], on=["q", "r"], how="left"
    )
    stats["league_fg"] = stats["league_fg"].fillna(league["shot_made_flag"].mean())

    stats["fg"] = stats["makes"] / stats["attempts"]
    # Shrink toward the league: 2 makes on 2 shots is evidence, not proof of a 100% shooter.
    stats["fg_adjusted"] = (stats["makes"] + PRIOR_SHOTS * stats["league_fg"]) / (
        stats["attempts"] + PRIOR_SHOTS
    )
    stats["diff"] = stats["fg_adjusted"] - stats["league_fg"]

    reference = max(stats["attempts"].quantile(0.9), 1)
    stats["size"] = np.clip(np.sqrt(stats["attempts"] / reference), MIN_SIZE, 1)
    stats["x"], stats["y"] = hex_centre(stats["q"].to_numpy(), stats["r"].to_numpy())
    return stats[(stats["y"] <= 422.5) & (stats["x"].abs() <= 250)]


def hexagon(x: float, y: float, scale: float) -> tuple[list[float], list[float]]:
    """Corner points of one pointy-top hexagon, closed, ending with a gap so many fit in one trace."""
    radius = HEX_RADIUS * scale * 0.95  # a sliver of floor between neighbours
    angles = [math.radians(30 + 60 * i) for i in range(7)]
    return [x + radius * math.cos(a) for a in angles] + [None], [
        y + radius * math.sin(a) for a in angles
    ] + [None]


def polygons(group: pd.DataFrame, grow: float = 1.0) -> tuple[list, list]:
    """Every hexagon in the group as one long outline, broken by gaps, so one trace can draw them all."""
    xs, ys = [], []
    for row in group.itertuples():
        hx, hy = hexagon(row.x, row.y, row.size * grow)
        xs += hx
        ys += hy
    return xs, ys


def hexbin_figure(
    stats: pd.DataFrame, colour_scale: list, relative: bool
) -> tuple[go.Figure, list[list[int]]]:
    """Draw the hexagons. relative=True colours by FG% vs the league; False by raw FG%.

    Also returns which traces should glow: one [halo trace, hexagon trace] pair per hot colour step.
    """
    if relative:
        values, low, high = stats["diff"], -DIFF_RANGE, DIFF_RANGE
        bar = dict(
            title="vs league",
            tickvals=[low, 0, high],
            ticktext=["−10 pts", "Even", "+10 pts"],
        )
    else:
        values, low, high = stats["fg"], 0.25, 0.65
        bar = dict(title="FG%", tickformat=".0%")

    # Plotly fills a whole trace with one colour, so hexagons are grouped into colour steps.
    edges = np.linspace(low, high, COLOUR_STEPS + 1)
    steps = np.clip(np.digitize(values, edges) - 1, 0, COLOUR_STEPS - 1)
    colours = sample_colorscale(
        colour_scale, [(i + 0.5) / COLOUR_STEPS for i in range(COLOUR_STEPS)]
    )
    hot_steps = [
        step
        for step in range(COLOUR_STEPS - GLOW_STEPS, COLOUR_STEPS)
        if (steps == step).any()
    ]

    fig = go.Figure()
    # Halos first, so they sit underneath every hexagon and only show as a soft rim.
    halo_index = {}
    for step in hot_steps:
        xs, ys = polygons(stats[steps == step], HALO_SIZE)
        halo_index[step] = len(fig.data)
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor=colours[step],
                line=dict(width=0),
                opacity=0.01,
                hoverinfo="skip",
                showlegend=False,
            )
        )

    glow = []
    for step, colour in enumerate(colours):
        group = stats[steps == step]
        if group.empty:
            continue
        xs, ys = polygons(group)
        if step in halo_index:
            glow.append([halo_index[step], len(fig.data)])
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor=colour,
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # An invisible marker on every hexagon carries the hover text.
    fig.add_trace(
        go.Scatter(
            x=stats["x"],
            y=stats["y"],
            mode="markers",
            marker=dict(size=14, opacity=0),
            customdata=stats[["attempts", "fg", "league_fg"]],
            hovertemplate=(
                "Shots: %{customdata[0]}<br>FG%: %{customdata[1]:.1%}"
                "<br>League from here: %{customdata[2]:.1%}<extra></extra>"
            ),
            showlegend=False,
        )
    )
    # A point-less trace that only draws the colour bar.
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            showlegend=False,
            hoverinfo="skip",
            marker=dict(
                colorscale=colour_scale,
                cmin=low,
                cmax=high,
                color=[low],
                showscale=True,
                colorbar=bar,
            ),
        )
    )
    return fig, glow


GLOW_PAGE = """<!doctype html>
<html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Barlow+Condensed:wght@700&display=swap">
<style>
  body {{ margin: 0; background: {background}; }}
  .glow-halo {{ animation: halo 2.6s ease-in-out infinite; }}
  .glow-core {{ animation: core 2.6s ease-in-out infinite; }}
  @keyframes halo {{ 0%, 100% {{ opacity: 0; }} 50% {{ opacity: 0.5; }} }}
  @keyframes core {{ 0%, 100% {{ opacity: 0.78; }} 50% {{ opacity: 1; }} }}
  @media (prefers-reduced-motion: reduce) {{
    .glow-halo, .glow-core {{ animation: none; }}
    .glow-halo {{ opacity: 0.3; }}
  }}
</style>
</head><body>{chart}</body></html>"""

GLOW_SCRIPT = """
var chart = document.getElementById('{plot_id}');
var GLOW = __GLOW__;
function markGlowing() {
  var traces = chart.querySelectorAll('.scatterlayer .trace');
  GLOW.forEach(function (pair, n) {
    var delay = (n * 0.45) + 's';
    var halo = traces[pair[0]], core = traces[pair[1]];
    if (halo) { halo.classList.add('glow-halo'); halo.style.animationDelay = delay; }
    if (core) { core.classList.add('glow-core'); core.style.animationDelay = delay; }
  });
}
markGlowing();
chart.on('plotly_afterplot', markGlowing);
"""


def glowing_chart_html(
    fig: go.Figure, glow: list[list[int]], config: dict, background: str, height: int
) -> str:
    """A self-contained page with the chart and a looping glow on the hottest hexagons. Starts on its own."""
    chart = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={**config, "responsive": True},
        default_height=f"{height}px",
        div_id="shot-chart",
        post_script=GLOW_SCRIPT.replace("__GLOW__", json.dumps(glow)),
    )
    return GLOW_PAGE.format(background=background, chart=chart)
