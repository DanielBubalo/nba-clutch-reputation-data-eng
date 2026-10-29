"""Hexbin shot charts: hexagon size shows shot volume, colour shows FG% against a baseline from that spot.

Coordinates are nba_api's, in tenths of a foot with the hoop at (0, 0) (see court.py).
"""

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
from plotly.colors import sample_colorscale  # type: ignore
from plotly.offline import get_plotlyjs_version  # type: ignore

HEX_RADIUS = 13  # centre to corner, in tenths of a foot: hexagons about 2.3 ft across
PRIOR_SHOTS = (
    5  # small samples are pulled toward the league by this many "average" shots
)
MIN_SIZE = 0.3  # the smallest hexagon drawn, as a share of full size
DIFF_RANGE = 0.10  # colour scale runs from 10 points below the league to 10 above
COLOUR_STEPS = 11
GLOW_STEPS = 3  # the hottest colour steps pulse and get a halo
HALO_SIZE = 1.45  # a halo is this much bigger than its hexagon
# The shot charts only use scatter traces, so they load Plotly's basic build (about 1.2 MB instead of
# 4.6 MB), at the same version the installed plotly package draws with.
PLOTLY_JS = (
    "https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@"
    f"{get_plotlyjs_version()}/plotly-basic.min.js"
)


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


def hex_stats(
    selected: pd.DataFrame, baseline: pd.DataFrame, league: pd.DataFrame | None = None
) -> pd.DataFrame:
    """One row per hexagon the selection shot from: volume, FG%, the baseline's FG% there, and the difference.

    baseline is what the selection is compared with: every clutch shot in the league, or the same
    player's other seasons. A player's other seasons are thin in most spots, so when league is given,
    the baseline's FG% in each hexagon is first pulled toward the league's there, the same way the
    selection is pulled toward the baseline.
    """
    base = hex_counts(baseline).rename(
        columns={"attempts": "base_attempts", "makes": "base_makes"}
    )
    if league is not None:
        league_hexes = hex_counts(league)
        league_hexes["league_fg"] = league_hexes["makes"] / league_hexes["attempts"]
        base = base.merge(
            league_hexes[["q", "r", "league_fg"]], on=["q", "r"], how="left"
        )
        base["league_fg"] = base["league_fg"].fillna(league["shot_made_flag"].mean())
        base["base_fg"] = (base["base_makes"] + PRIOR_SHOTS * base["league_fg"]) / (
            base["base_attempts"] + PRIOR_SHOTS
        )
    else:
        base["base_fg"] = base["base_makes"] / base["base_attempts"]

    stats = hex_counts(selected).merge(
        base[["q", "r", "base_fg", "base_attempts", "base_makes"]],
        on=["q", "r"],
        how="left",
    )
    stats["base_attempts"] = stats["base_attempts"].fillna(0).astype(int)
    stats["base_makes"] = stats["base_makes"].fillna(0).astype(int)
    if league is not None:
        # The baseline never shot from here, so the best guess for it is the league from this spot.
        stats = stats.merge(
            league_hexes[["q", "r", "league_fg"]], on=["q", "r"], how="left"
        )
        stats["base_fg"] = stats["base_fg"].fillna(stats["league_fg"])
        stats["base_fg"] = stats["base_fg"].fillna(league["shot_made_flag"].mean())
    else:
        stats["base_fg"] = stats["base_fg"].fillna(baseline["shot_made_flag"].mean())

    stats["fg"] = stats["makes"] / stats["attempts"]
    # Shrink toward the baseline: 2 makes on 2 shots is evidence, not proof of a 100% shooter.
    stats["fg_adjusted"] = (stats["makes"] + PRIOR_SHOTS * stats["base_fg"]) / (
        stats["attempts"] + PRIOR_SHOTS
    )
    stats["diff"] = stats["fg_adjusted"] - stats["base_fg"]

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


def hover_text(stats: pd.DataFrame, baseline_label: str) -> list[str]:
    """Raw makes and attempts on both sides. The colour uses the adjusted numbers; the hover shows the facts."""
    lines = []
    for row in stats.itertuples():
        line = f"Shots: {row.attempts:,}<br>Made: {row.makes:,} ({row.fg:.1%})"
        if row.base_attempts:
            line += (
                f"<br>{baseline_label} from here: {row.base_makes:,} of {row.base_attempts:,} "
                f"({row.base_makes / row.base_attempts:.1%})"
            )
        else:
            line += (
                f"<br>{baseline_label}: no shots from here,"
                f"<br>so the league's {row.base_fg:.1%} from this spot stands in"
            )
        lines.append(line)
    return lines


def colorbar(**ticks) -> dict:
    """Colour bar styling shared by the shot charts: a slim bar with its labels set off from it.

    There's no title: Plotly misplaces a colour bar title when the chart is built inside a hidden tab
    (it lands on the bar), so what a title would say goes into the tick labels instead.
    """
    return dict(
        thickness=14,
        len=0.75,
        y=0.45,
        yanchor="middle",
        ticks="outside",
        ticklen=8,
        tickcolor="rgba(0,0,0,0)",  # invisible ticks: they only push the labels away from the bar
        outlinewidth=0,
        **ticks,
    )


def hexbin_figure(
    stats: pd.DataFrame,
    colour_scale: list,
    relative: bool,
    baseline_label: str = "League",
) -> tuple[go.Figure, list[list[int]]]:
    """Draw the hexagons. relative=True colours by FG% vs the baseline; False by raw FG%.

    baseline_label names the baseline in the colour bar and hover text, e.g. "League" or "Other seasons".

    Also returns which traces should glow: one [halo trace, hexagon trace] pair per hot colour step.
    """
    if relative:
        values, low, high = stats["diff"], -DIFF_RANGE, DIFF_RANGE
        bar = colorbar(
            tickvals=[low, 0, high],
            ticktext=["−10 pts", f"Same as {baseline_label.lower()}", "+10 pts"],
        )
    else:
        values, low, high = stats["fg"], 0.25, 0.65
        fg_ticks = [0.25, 0.35, 0.45, 0.55, 0.65]
        bar = colorbar(
            tickvals=fg_ticks, ticktext=[f"FG {tick:.0%}" for tick in fg_ticks]
        )

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
            hovertext=hover_text(stats, baseline_label),
            hoverinfo="text",
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
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" media="print" onload="this.media='all'" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Barlow+Condensed:wght@700&display=swap">
<style>
  html, body {{ margin: 0; background: {background}; }}
  /* Invisible until on screen and drawn at its real size, so switching tabs doesn't jump. */
  #shot-chart {{ opacity: 0; }}
  .ready #shot-chart {{ opacity: 1; transition: opacity 0.2s; }}
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

# Shared by both shot chart pages (hexagons here, zones in zones.py). A chart built inside a hidden tab
# has no size, so Plotly measures all text as zero and misplaces it (the colour bar title lands on the
# bar). So the first real draw waits until the page actually has a size, and the chart redraws whenever
# it goes from hidden to shown, which the browser reports as a resize. Each page defines chart,
# onFirstShow() and afterPlot() (reapplies the animation classes after a draw) before this runs.
SHOW_WHEN_VISIBLE_JS = """
var CONFIG = __CONFIG__;
var firstShowStarted = false, firstShowDone = false, resizeTimer = null;
function visibleNow() {
  return window.innerWidth > 0 && window.innerHeight > 0 && chart.offsetWidth > 0;
}
function redraw() {
  // Rebuild the chart from scratch, one frame after the page has its size. A resize or redraw keeps
  // text measurements taken while hidden; a fresh build measures everything again, like a chart that
  // was built while its tab was open.
  return new Promise(function (resolve) { requestAnimationFrame(resolve); }).then(function () {
    return Plotly.newPlot(chart, chart.data, chart.layout, CONFIG);
  }).then(function () {
    // newPlot throws away the old SVG (and the classes on it) and removes every chart.on listener,
    // so hook afterPlot back up and run it once for this draw, which the old listener never saw.
    chart.on('plotly_afterplot', afterPlot);
    afterPlot();
  });
}
function firstShow() {
  if (firstShowStarted || !visibleNow()) return;
  firstShowStarted = true;
  function finish() { firstShowDone = true; onFirstShow(); }
  // Wait for the web font too, so text is measured in the font it will be shown in.
  document.fonts.ready.then(redraw).then(finish, finish);
}
window.addEventListener('resize', function () {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () {
    if (!firstShowStarted) firstShow();
    else if (firstShowDone && visibleNow()) redraw();
  }, 120);
});
document.fonts.addEventListener('loadingdone', function () {
  if (firstShowDone && visibleNow()) redraw();
});
if ('IntersectionObserver' in window) {
  new IntersectionObserver(function (entries, observer) {
    // intersectionRatio, not isIntersecting: a page with no size still counts as "intersecting".
    if (entries.some(function (entry) { return entry.intersectionRatio > 0; }) && visibleNow()) {
      observer.disconnect();
      firstShow();
    }
  }).observe(chart);
}
firstShow();  // already on screen, e.g. the tab was open when the chart was built
"""

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
function afterPlot() { markGlowing(); }
markGlowing();
chart.on('plotly_afterplot', afterPlot);
function onFirstShow() { document.body.classList.add('ready'); }
""" + SHOW_WHEN_VISIBLE_JS


def glowing_chart_html(
    fig: go.Figure, glow: list[list[int]], config: dict, background: str, height: int
) -> str:
    """A self-contained page with the chart and a looping glow on the hottest hexagons. Starts on its own."""
    config = {**config, "responsive": True}
    chart = fig.to_html(
        full_html=False,
        include_plotlyjs=PLOTLY_JS,
        config=config,
        default_height=f"{height}px",
        div_id="shot-chart",
        post_script=GLOW_SCRIPT.replace("__GLOW__", json.dumps(glow)).replace(
            "__CONFIG__", json.dumps(config)
        ),
    )
    return GLOW_PAGE.format(background=background, chart=chart)
