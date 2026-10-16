"""The dashboard's broadcast look: colours, the chart style, and the scoreboard strip.

Colours live here once so every chart, table and panel uses the same ones.
The page itself (background, fonts, widgets) is themed in .streamlit/config.toml.
"""

import plotly.graph_objects as go
import plotly.io as pio

NAVY = "#0D1B2A"  # page background: the arena with the lights down
PANEL = "#15273C"  # raised surfaces
LINE = "#2A3F57"  # gridlines and dividers
TEXT = "#E8EEF4"
MUTED = "#8DA0B3"

TIER_ORDER = ["Role", "Olympic Gold Medalist", "Star"]
TIER_COLOURS = {
    "Role": "#6C8EBF",
    "Olympic Gold Medalist": "#F5C451",
    "Star": "#FF5A36",
}
TIER_PLURALS = {
    "Role": "Role players",
    "Olympic Gold Medalist": "Olympic Gold Medalists",
    "Star": "Stars",
}

# Hot and cold zones, the way broadcasts show shooting: blue is cold, orange is hot.
HOT_COLD = [[0.0, "#2F6DB5"], [0.5, "#9AA8B6"], [1.0, "#FF5A36"]]

# Passed to every st.plotly_chart: hides the floating toolbar.
PLOTLY_CONFIG = {"displayModeBar": False}

pio.templates["broadcast"] = go.layout.Template(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow, sans-serif", color=TEXT, size=14),
        title=dict(
            font=dict(family="Barlow Condensed, sans-serif", size=22),
            x=0,
            xanchor="left",
        ),
        colorway=[TIER_COLOURS[tier] for tier in TIER_ORDER],
        xaxis=dict(gridcolor=LINE, linecolor=LINE, zerolinecolor=LINE),
        yaxis=dict(gridcolor=LINE, linecolor=LINE, zerolinecolor=LINE),
        hoverlabel=dict(
            bgcolor=PANEL,
            bordercolor=LINE,
            font=dict(family="Barlow, sans-serif", color=TEXT),
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=50, b=10),
    )
)
pio.templates.default = "plotly_dark+broadcast"

CSS = f"""
<style>
.scoreboard {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2px;
    background: {LINE};
    border-radius: 6px;
    overflow: hidden;
    margin: 0.5rem 0 1.25rem;
}}
.score {{
    background: {PANEL};
    padding: 0.9rem 1.25rem 1rem;
    border-top: 4px solid var(--tier);
}}
.score-name {{
    font-family: "Barlow Condensed", sans-serif;
    font-weight: 600;
    font-size: 1.15rem;
    color: {MUTED};
}}
.score-value {{
    font-family: "Barlow Condensed", sans-serif;
    font-weight: 700;
    font-size: 3.6rem;
    line-height: 1;
    color: {TEXT};
    font-variant-numeric: tabular-nums;
}}
.score-value small {{
    font-size: 1.2rem;
    font-weight: 600;
    color: {MUTED};
    margin-left: 0.3rem;
}}
.score-meta {{
    color: {MUTED};
    font-size: 0.9rem;
    margin-top: 0.35rem;
}}
.score.lowest .score-name {{
    color: var(--tier);
}}
.brand {{
    font-family: "Barlow Condensed", sans-serif;
    font-weight: 700;
    font-size: 1.7rem;
    line-height: 1.05;
    color: {TEXT};
}}
.brand-sub {{
    color: {MUTED};
    font-size: 0.92rem;
    margin: 0.35rem 0 0.5rem;
}}
@media (max-width: 640px) {{
    .scoreboard {{ grid-template-columns: 1fr; }}
}}
</style>
"""


def scoreboard_html(summary) -> str:
    """One panel per tier, like a broadcast score bug: mean clutch change in true shooting points."""
    lowest = summary["mean_ts_delta"].idxmin()
    panels = []
    for index, row in summary.iterrows():
        points = row.mean_ts_delta * 100
        value = f"{points:+.1f}".replace("-", "\u2212")
        note = "Biggest drop. " if index == lowest else ""
        panels.append(
            f'<div class="score{" lowest" if index == lowest else ""}" '
            f'style="--tier: {TIER_COLOURS[row.group_tier]}">'
            f'<div class="score-name">{TIER_PLURALS[row.group_tier]}</div>'
            f'<div class="score-value">{value}<small>TS pts</small></div>'
            f'<div class="score-meta">{note}{int(row.n):,} player-seasons</div>'
            "</div>"
        )
    return f'<div class="scoreboard">{"".join(panels)}</div>'
