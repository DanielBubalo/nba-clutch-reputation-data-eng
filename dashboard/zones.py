"""Zone shot charts: compare one season with a baseline zone by zone, for when hexagons are too thin.

A single season has only a few clutch shots in most hexagons, so comparing two seasons hexagon by
hexagon is mostly noise. The court is split into five zones instead, using the same lines court.py
draws, so each zone holds enough shots to compare. Coordinates are nba_api's: tenths of a foot,
hoop at (0, 0).
"""

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
from plotly.colors import sample_colorscale, unlabel_rgb  # type: ignore

from hexbin import DIFF_RANGE, PLOTLY_JS, PRIOR_SHOTS, SHOW_WHEN_VISIBLE_JS, colorbar

ZONES = [
    "Restricted area",
    "Paint (non-RA)",
    "Mid-range",
    "Corner 3",
    "Above the break 3",
]
# Where each zone's label sits on the court. Corners are too narrow for text; their numbers are in
# the hover and the table.
LABEL_AT = {
    "Restricted area": (0, 14),
    "Paint (non-RA)": (0, 95),
    "Mid-range": (-150, 130),
    "Above the break 3": (0, 320),
}
HOVER_STEP = 10  # one invisible hover point per foot, so hovering anywhere in a zone shows its numbers
HOT_DIFF = (
    0.04  # zones at least 4 points better than the comparison (after adjustment) pulse
)
NO_SHOTS = (
    "#1B2A3A"  # zones he didn't shoot from: a quiet panel, not a colour on the scale
)


def zone_of(x, y) -> np.ndarray:
    """Which zone each location is in, using the court's own lines."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    distance = np.hypot(x, y)
    corner = (np.abs(x) >= 220) & (y <= 92.5)
    above_break = ~corner & (distance >= 237.5)
    restricted = ~corner & ~above_break & (distance < 40)
    paint = ~corner & ~above_break & ~restricted & (np.abs(x) < 80) & (y < 142.5)
    return np.select(
        [corner, above_break, restricted, paint],
        ["Corner 3", "Above the break 3", "Restricted area", "Paint (non-RA)"],
        default="Mid-range",
    )


def zone_counts(shots: pd.DataFrame) -> pd.DataFrame:
    """Attempts and makes per zone, with every zone present even if nobody shot from it."""
    counts = (
        pd.DataFrame(
            {
                "zone": zone_of(shots["loc_x"], shots["loc_y"]),
                "made": shots["shot_made_flag"].to_numpy(),
            }
        )
        .groupby("zone")["made"]
        .agg(attempts="size", makes="sum")
    )
    return counts.reindex(ZONES, fill_value=0).rename_axis("zone").reset_index()


def zone_stats(
    selected: pd.DataFrame, baseline: pd.DataFrame, league_zones: pd.DataFrame
) -> pd.DataFrame:
    """One row per zone: volume and FG% for the selection and the baseline, and the adjusted difference.

    league_zones is zone_counts() of every clutch shot, passed in so the app can compute it once.
    Same rules as the hexagons: the baseline is pulled toward the league by PRIOR_SHOTS, and the
    selection toward the baseline, so a zone with 2 shots can't look like a hot streak.
    """
    league_fg = league_zones["makes"] / league_zones["attempts"].replace(0, np.nan)
    league_fg = league_fg.fillna(
        league_zones["makes"].sum() / max(league_zones["attempts"].sum(), 1)
    )

    stats = zone_counts(selected)
    base = zone_counts(baseline)
    stats["base_attempts"], stats["base_makes"] = base["attempts"], base["makes"]
    stats["league_fg"] = league_fg

    stats["share"] = stats["attempts"] / max(stats["attempts"].sum(), 1)
    stats["base_share"] = stats["base_attempts"] / max(stats["base_attempts"].sum(), 1)
    stats["fg"] = stats["makes"] / stats["attempts"].replace(0, np.nan)
    stats["base_fg_raw"] = stats["base_makes"] / stats["base_attempts"].replace(
        0, np.nan
    )
    stats["base_fg"] = (stats["base_makes"] + PRIOR_SHOTS * stats["league_fg"]) / (
        stats["base_attempts"] + PRIOR_SHOTS
    )
    stats["fg_adjusted"] = (stats["makes"] + PRIOR_SHOTS * stats["base_fg"]) / (
        stats["attempts"] + PRIOR_SHOTS
    )
    # No shots in a zone means nothing to compare, so it stays uncoloured.
    stats["diff"] = (stats["fg_adjusted"] - stats["base_fg"]).where(
        stats["attempts"] > 0
    )
    return stats


def zone_hover(row, baseline_label: str) -> str:
    """Raw makes and attempts on both sides, plus how much of each side's shooting came from here."""
    text = f"<b>{row.zone}</b><br>"
    if row.attempts:
        text += f"This season: {row.makes} of {row.attempts} ({row.fg:.1%}), {row.share:.0%} of his shots"
    else:
        text += "This season: no shots from here"
    if row.base_attempts:
        text += (
            f"<br>{baseline_label}: {row.base_makes} of {row.base_attempts} "
            f"({row.base_fg_raw:.1%}), {row.base_share:.0%} of his shots"
        )
    else:
        text += (
            f"<br>{baseline_label}: no shots from here,"
            f"<br>so the league's {row.league_fg:.1%} from this zone stands in"
        )
    return text


def arc_points(
    radius: float, start_deg: float, end_deg: float, points: int = 80
) -> list[tuple]:
    """Points along a circle around the hoop, matching how court.py draws its arcs."""
    return [
        (
            radius
            * math.cos(math.radians(start_deg + (end_deg - start_deg) * i / points)),
            radius
            * math.sin(math.radians(start_deg + (end_deg - start_deg) * i / points)),
        )
        for i in range(points + 1)
    ]


def zone_polygons() -> list[tuple[str, list[tuple]]]:
    """Each zone as an outline, back to front. Later zones are drawn on top of earlier ones, so no
    shape needs a hole: the paint sits on mid-range, and the restricted area on the paint.
    """
    corner_angle = math.degrees(math.acos(220 / 237.5))
    inside_arc = (
        [(220, -47.5)]
        + arc_points(237.5, corner_angle, 180 - corner_angle)
        + [(-220, -47.5)]
    )
    return [
        (
            "Above the break 3",
            [(-250, -47.5), (250, -47.5), (250, 422.5), (-250, 422.5)],
        ),
        ("Corner 3", [(220, -47.5), (250, -47.5), (250, 92.5), (220, 92.5)]),
        ("Corner 3", [(-250, -47.5), (-220, -47.5), (-220, 92.5), (-250, 92.5)]),
        ("Mid-range", inside_arc),
        ("Paint (non-RA)", [(-80, -47.5), (80, -47.5), (80, 142.5), (-80, 142.5)]),
        ("Restricted area", arc_points(40, 0, 360)),
    ]


def zone_colour(diff: float, colour_scale: list, background: str) -> str:
    """The colour-scale colour for a difference, mixed with the background so fills stay opaque
    (stacked see-through fills would blend into each other)."""
    if pd.isna(diff):
        return NO_SHOTS
    position = (np.clip(diff, -DIFF_RANGE, DIFF_RANGE) + DIFF_RANGE) / (2 * DIFF_RANGE)
    colour = unlabel_rgb(sample_colorscale(colour_scale, [position])[0])
    back = tuple(int(background.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    mixed = [round(0.88 * c + 0.12 * b) for c, b in zip(colour, back)]
    return f"rgb({mixed[0]}, {mixed[1]}, {mixed[2]})"


def zone_figure(
    stats: pd.DataFrame, colour_scale: list, baseline_label: str, background: str
) -> tuple[go.Figure, list[int], list[int]]:
    """The court painted zone by zone: colour is the adjusted FG% difference, labels give both FG%s.

    Also returns the zone traces in the order they should appear (rim outward) and which ones are hot.
    """
    by_zone = stats.set_index("zone")
    fig = go.Figure()
    zone_traces, hot_traces = [], []
    for zone, points in zone_polygons():
        diff = by_zone.loc[zone, "diff"]
        xs, ys = zip(*points)
        if not pd.isna(diff) and diff >= HOT_DIFF:
            hot_traces.append(len(fig.data))
        zone_traces.append(len(fig.data))
        fig.add_trace(
            go.Scatter(
                x=list(xs) + [xs[0]],
                y=list(ys) + [ys[0]],
                mode="lines",
                fill="toself",
                fillcolor=zone_colour(diff, colour_scale, background),
                line=dict(
                    color=background, width=3
                ),  # a thin gap between zones, like tiles
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Invisible points carry the hover text, one trace per zone, so each zone's text is stored once.
    xs = np.arange(-245, 250, HOVER_STEP)
    ys = np.arange(-42.5, 420, HOVER_STEP)
    grid_x, grid_y = (grid.ravel() for grid in np.meshgrid(xs, ys))
    grid_zone = zone_of(grid_x, grid_y)
    for row in stats.itertuples():
        inside = grid_zone == row.zone
        fig.add_trace(
            go.Scatter(
                x=grid_x[inside],
                y=grid_y[inside],
                mode="markers",
                marker=dict(size=HOVER_STEP, opacity=0),
                hovertext=zone_hover(row, baseline_label),
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
                cmin=-DIFF_RANGE,
                cmax=DIFF_RANGE,
                color=[0],
                showscale=True,
                colorbar=colorbar(
                    tickvals=[-DIFF_RANGE, 0, DIFF_RANGE],
                    ticktext=[
                        "−10 pts",
                        f"Same as {baseline_label.lower()}",
                        "+10 pts",
                    ],
                ),
            ),
        )
    )

    for zone, (x, y) in LABEL_AT.items():
        row = by_zone.loc[zone]
        if row["attempts"]:
            base = f"{row['base_fg_raw']:.0%}" if row["base_attempts"] else "no shots"
            label = (
                f"<span style='font-family:Barlow Condensed;font-size:20px'><b>{row['fg']:.0%}</b></span>"
                f"  vs {base}<br>{row['makes']:.0f}/{row['attempts']:.0f} shots"
            )
        else:
            label = "no shots"
        fig.add_annotation(
            x=x,
            y=y,
            text=label,
            showarrow=False,
            font=dict(family="Barlow, sans-serif", size=12, color="#FFFFFF"),
            bgcolor="rgba(13, 27, 42, 0.55)",
            borderpad=5,
        )
    fig.update_layout(
        font=dict(family="Barlow, sans-serif"), hoverlabel=dict(font_family="Barlow")
    )
    # Rim outward: the reverse of the drawing order.
    return fig, zone_traces[::-1], hot_traces


ZONE_PAGE = """<!doctype html>
<html><head>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" media="print" onload="this.media='all'" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Barlow+Condensed:wght@700&display=swap">
<style>
  html, body {{ margin: 0; background: {background}; }}
  /* The chart stays invisible until it is on screen and drawn at its real size, so nothing jumps. */
  #zone-chart {{ opacity: 0; }}
  .ready #zone-chart {{ opacity: 1; transition: opacity 0.15s; }}
  .scatterlayer .trace {{ opacity: 0; }}
  .zone-shown {{ opacity: 1; }}
  .zone-hot-shown {{ opacity: 1; animation: zone-hot 2.4s ease-in-out infinite; }}
  .zone-in {{ animation: zone-in 0.35s ease-out forwards; }}
  .zone-hot-in {{ animation: zone-in 0.35s ease-out forwards, zone-hot 2.4s ease-in-out infinite; }}
  .annotation {{ opacity: 0; }}
  .ready .annotation {{ animation: zone-in 0.3s ease-out 0.45s forwards; }}
  .settled .annotation {{ opacity: 1; animation: none; }}
  @keyframes zone-in {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  @keyframes zone-hot {{
    0%, 100% {{ filter: brightness(1); }}
    50% {{ filter: brightness(1.3) drop-shadow(0 0 10px rgba(255, 90, 54, 0.85)); }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .zone-in, .zone-hot-in, .zone-hot-shown, .ready .annotation {{ animation: none; opacity: 1; }}
  }}
</style>
</head><body>{chart}</body></html>"""

ZONE_SCRIPT = """
var chart = document.getElementById('{plot_id}');
var ORDER = __ORDER__, HOT = __HOT__;
var shown = false;
function markZones(animate) {
  var traces = chart.querySelectorAll('.scatterlayer .trace');
  ORDER.forEach(function (index, n) {
    var trace = traces[index];
    if (!trace) return;
    var hot = HOT.indexOf(index) >= 0;
    if (animate) {
      // Rim outward, 70 ms apart; a hot zone starts pulsing once it has faded in.
      var delay = n * 0.07;
      trace.classList.add(hot ? 'zone-hot-in' : 'zone-in');
      trace.style.animationDelay = hot ? delay + 's, ' + (delay + 0.5) + 's' : delay + 's';
    } else {
      // Later redraws (a resize) show the zones straight away: the fade only ever plays once.
      trace.classList.add(hot ? 'zone-hot-shown' : 'zone-shown');
    }
  });
}
function start() {
  if (shown) return;
  shown = true;
  document.body.classList.add('ready');
  markZones(true);
  setTimeout(function () { document.body.classList.add('settled'); }, 900);
}
function afterPlot() { if (shown) markZones(false); }
chart.on('plotly_afterplot', afterPlot);
function onFirstShow() { start(); }
""" + SHOW_WHEN_VISIBLE_JS


def zone_chart_html(
    fig: go.Figure,
    order: list[int],
    hot: list[int],
    config: dict,
    background: str,
    height: int,
) -> str:
    """A self-contained page: zones fade in from the rim outward, labels follow, and hot zones pulse."""
    config = {**config, "responsive": True}
    chart = fig.to_html(
        full_html=False,
        include_plotlyjs=PLOTLY_JS,
        config=config,
        default_height=f"{height}px",
        div_id="zone-chart",
        post_script=ZONE_SCRIPT.replace("__ORDER__", json.dumps(order))
        .replace("__HOT__", json.dumps(hot))
        .replace("__CONFIG__", json.dumps(config)),
    )
    return ZONE_PAGE.format(background=background, chart=chart)
