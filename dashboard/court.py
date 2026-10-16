"""Draw an NBA half-court as Plotly shapes, in the shot-chart coordinate system.

nba_api's shot locations are in tenths of a foot, with the hoop at (0, 0):
x runs from -250 (one sideline) to 250 (the other), and y from -47.5 (the baseline)
to 422.5 (half court).
"""

import math

import plotly.graph_objects as go

LINE = dict(color="rgba(232, 238, 244, 0.35)", width=1.5)

X_RANGE = (-250, 250)
Y_RANGE = (-47.5, 422.5)


def arc(
    x_centre: float,
    y_centre: float,
    radius: float,
    start_deg: float,
    end_deg: float,
    points: int = 60,
) -> str:
    """An SVG path for part of a circle, which Plotly can draw as a shape."""
    coords = []
    for i in range(points + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / points)
        coords.append(
            (x_centre + radius * math.cos(angle), y_centre + radius * math.sin(angle))
        )
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in coords)


def court_shapes() -> list[dict]:
    # The three-point arc meets the corner lines (x = ±220) at this angle.
    corner_angle = math.degrees(math.acos(220 / 237.5))
    return [
        # outline: baseline, sidelines, half-court line
        dict(type="rect", x0=-250, y0=-47.5, x1=250, y1=422.5, line=LINE),
        # hoop and backboard
        dict(type="circle", x0=-7.5, y0=-7.5, x1=7.5, y1=7.5, line=LINE),
        dict(type="line", x0=-30, y0=-7.5, x1=30, y1=-7.5, line=LINE),
        # the paint (outer and inner boxes)
        dict(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line=LINE),
        dict(type="rect", x0=-60, y0=-47.5, x1=60, y1=142.5, line=LINE),
        # free-throw circle and restricted area
        dict(type="path", path=arc(0, 142.5, 60, 0, 180), line=LINE),
        dict(type="path", path=arc(0, 0, 40, 0, 180), line=LINE),
        # three-point line: two straight corner lines and the arc
        dict(type="line", x0=-220, y0=-47.5, x1=-220, y1=92.5, line=LINE),
        dict(type="line", x0=220, y0=-47.5, x1=220, y1=92.5, line=LINE),
        dict(
            type="path",
            path=arc(0, 0, 237.5, corner_angle, 180 - corner_angle),
            line=LINE,
        ),
        # centre circles at half court
        dict(type="path", path=arc(0, 422.5, 60, 180, 360), line=LINE),
        dict(type="path", path=arc(0, 422.5, 20, 180, 360), line=LINE),
    ]


def draw_court(fig: go.Figure) -> go.Figure:
    """Add the court lines to a figure and lock the axes so the court keeps its shape."""
    fig.update_layout(
        shapes=court_shapes(), height=620, margin=dict(l=10, r=10, t=40, b=10)
    )
    fig.update_xaxes(range=X_RANGE, visible=False)
    fig.update_yaxes(range=Y_RANGE, visible=False, scaleanchor="x", scaleratio=1)
    return fig
