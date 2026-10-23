"""Plain-language help: the glossary, the numbered notes on the Overview, and the Guide tab.

Every definition lives in GLOSSARY, so the sidebar, the Overview notes and the Guide tab can't drift
apart. The Overview notes are built from the same numbers the page shows, so they stay true when the
sidebar filters change.
"""

import math

import pandas as pd

from style import TIER_PLURALS

GLOSSARY = {
    "Clutch": "The last 5 minutes of the 4th quarter or overtime, with the score within 5 points. "
    "This is the NBA's official definition.",
    "True shooting (TS%)": "Scoring efficiency that counts threes and free throws, not just field goals: "
    "points divided by 2 × (field goal attempts + 0.44 × free throw attempts).",
    "ts_delta": "Clutch TS% minus the same player's full-season TS%, for one season. Negative means he "
    "shot worse in the clutch than he usually does. Each player is compared with himself, not with "
    "other players.",
    "TS points": "ts_delta in percentage points. −1.5 means a 58.0% shooter shoots about 56.5% in the clutch.",
    "Usage": "The share of a team's plays a player finishes (a shot, a free-throw trip or a turnover) "
    "while he's on the floor. usg_delta is clutch usage minus full-season usage.",
    "Tiers": "Star: won a star-level NBA award before that season. Olympic Gold Medalist: a star-level "
    "award plus an Olympic gold. Role: everyone else. Awards only count from the season after they're "
    "won, so a player becomes a Star the season after his first award.",
    "Player-season": "One player in one season: the unit everything is averaged over. The same player "
    "appears once per season he qualifies.",
    "Qualifying player-season": "At least 15 clutch games and more than 100 field goal attempts that season.",
    "Mean": "The average: add up every player-season's ts_delta and divide by how many there are.",
    "Median": "The middle player-season when they're lined up from worst to best. If it's close to the "
    "mean, a few extreme seasons aren't skewing the average.",
    "Std dev": "How far a single player-season typically lands from the average. Big here, because one "
    "season of clutch shots is a small, noisy sample.",
    "Error bar (95% interval)": "The range the true average probably falls in, given how much single seasons "
    "bounce around: the mean ± 1.96 standard errors. Many seasons give a short bar; few give a long one. "
    "The same player appears in many seasons, so the real uncertainty is somewhat larger than shown.",
    "Pulled toward the comparison": "On the shot charts, a spot or zone with few shots is blended with the "
    "comparison's numbers (as if it had 5 extra average shots), so one lucky make can't paint it hot.",
}

SIDEBAR_TERMS = [
    "Clutch",
    "True shooting (TS%)",
    "ts_delta",
    "Usage",
    "Tiers",
    "Qualifying player-season",
]

GUIDE_CSS = """
<style>
.guide {
    background: rgba(255, 90, 54, 0.07);
    border-radius: 6px;
    padding: 0.6rem 0.85rem;
    margin: 0 0 0.6rem;
    font-size: 0.92rem;
    line-height: 1.45;
}
.guide-start { border-left: 3px solid #FF5A36; border-radius: 0 6px 6px 0; margin-bottom: 0.9rem; }
.guide-head { display: flex; align-items: center; gap: 0.45rem; font-weight: 600; }
.guide-step {
    flex: none;
    width: 1.45rem;
    height: 1.45rem;
    border-radius: 50%;
    background: #FF5A36;
    color: #0D1B2A;
    font-weight: 700;
    font-size: 0.82rem;
    line-height: 1.45rem;
    text-align: center;
}
.guide-lead { margin-top: 0.2rem; opacity: 0.85; }
.guide-key {
    display: inline-block;
    margin-top: 0.4rem;
    padding: 0.15rem 0.55rem;
    border-radius: 4px;
    background: rgba(245, 196, 81, 0.14);
    color: #F5C451;
    font-weight: 600;
}
.guide details { margin-top: 0.35rem; }
.guide summary { cursor: pointer; opacity: 0.7; font-size: 0.85rem; }
.guide details p { margin: 0.35rem 0 0; opacity: 0.85; }
.chart-hint {
    display: inline-block;
    margin: 0.2rem 0 0.3rem;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    background: rgba(255, 90, 54, 0.1);
    font-size: 0.82rem;
    opacity: 0.9;
}
/* With "Explain this page" on, each explained part of the page sits in an orange-edged box. */
[class*="st-key-guide-"],
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [class*="st-key-guide-"]) {
    border-color: rgba(255, 90, 54, 0.55) !important;
}
</style>
"""


def glossary_markdown(terms: list[str] | None = None) -> str:
    """Glossary entries as markdown, all of them or just the named ones."""
    return "\n\n".join(f"**{term}:** {GLOSSARY[term]}" for term in (terms or GLOSSARY))


def _keep_spaces(html: str) -> str:
    """Streamlit drops a plain space next to an inline tag ("<i>usually</i> lowest" shows as
    "usuallylowest"), so spaces touching <b> or <i> become non-breaking spaces, which it keeps.
    """
    for tag in ("b", "i"):
        html = html.replace(f"</{tag}> ", f"</{tag}>&nbsp;").replace(
            f" <{tag}>", f"&nbsp;<{tag}>"
        )
    return html


def callout(
    step: int | None, title: str, lead: str, key: str = "", more: str = ""
) -> str:
    """One note: a numbered title, one short sentence, the key number right now, and the longer
    explanation folded away under "How to read it". step=None gives the unnumbered Start here note.
    """
    badge = f'<span class="guide-step">{step}</span>' if step else ""
    html = f'<div class="guide{" guide-start" if step is None else ""}">'
    html += f'<div class="guide-head">{badge}{title}</div><div class="guide-lead">{lead}</div>'
    if key:
        html += f'<div class="guide-key">{key}</div>'
    if more:
        html += f"<details><summary>How to read it</summary><p>{more}</p></details>"
    return _keep_spaces(html + "</div>")


def chart_hint(legend: str = "", zoom: bool = True) -> str:
    """The always-visible tip above an interactive chart: how to zoom, and what the legend does.
    legend names a legend entry ("a tier", "a line"); zoom=False leaves out the zoom tips.
    """
    tips = (
        ["<b>Drag</b> to zoom in", "<b>double-click</b> to zoom back out"]
        if zoom
        else []
    )
    if legend:
        tips.append(
            f"<b>click</b> {legend} in the legend to hide it, <b>double-click</b> it to show only that one"
        )
    return _keep_spaces(f'<div class="chart-hint">🔍 {" · ".join(tips)}</div>')


def _points(value: float) -> str:
    return f"{value * 100:+.2f}".replace("-", "\u2212")


def _short(value: float) -> str:
    return f"{value * 100:+.1f}".replace("-", "\u2212")


def _verdict(z: float) -> str:
    """What a gap of z standard errors means, in words."""
    if z < 1:
        return "easily explained by luck"
    if z < 2:
        return "could still be luck"
    if z < 3:
        return "unlikely to be luck alone, but not conclusive"
    return "strong evidence of a real difference"


def start_note(summary: pd.DataFrame) -> str:
    worst = summary.loc[summary["mean_ts_delta"].idxmin()]
    best = summary.loc[summary["mean_ts_delta"].idxmax()]
    key = f"{TIER_PLURALS[worst.group_tier]} {_points(worst.mean_ts_delta)}"
    if len(summary) > 1:
        key += f" · {TIER_PLURALS[best.group_tier]} {_points(best.mean_ts_delta)}"
    return callout(
        None,
        "Start here",
        "Every number compares a player with <b>himself</b>: clutch shooting minus his own full-season "
        "shooting. Negative means worse than he usually is. Notes 1 to 5 match the boxes below.",
        key,
    )


def scoreboard_note(summary: pd.DataFrame) -> str:
    worst = summary.loc[summary["mean_ts_delta"].idxmin()]
    clutch_ts = 58 + worst.mean_ts_delta * 100
    return callout(
        1,
        "The scoreboard",
        "One panel per tier: its average change in true shooting, in percentage points.",
        f"{TIER_PLURALS[worst.group_tier]} {_points(worst.mean_ts_delta)}: a 58% shooter hits about "
        f"{clutch_ts:.1f}% when it's close",
        "The small line under each big number is how many player-seasons it averages. More seasons "
        "means an average you can trust more.",
    )


def chart_note(summary: pd.DataFrame) -> str:
    key = ""
    if len(summary) > 1:
        worst = summary.loc[summary["mean_ts_delta"].idxmin()]
        best = summary.loc[summary["mean_ts_delta"].idxmax()]
        gap = best.mean_ts_delta - worst.mean_ts_delta
        se = math.sqrt((worst.ci95 / 1.96) ** 2 + (best.ci95 / 1.96) ** 2)
        if se > 0:
            z = gap / se
            key = (
                f"{TIER_PLURALS[worst.group_tier]} vs {TIER_PLURALS[best.group_tier]}: gap {gap * 100:.2f} pts, "
                f"{z:.1f}× its uncertainty → {_verdict(z)}"
            )
    return callout(
        2,
        "Is the difference real, or luck?",
        "The same averages as bars. The thin line on each bar shows how far that average could be off "
        "by luck.",
        key,
        "That line is the 95% interval. It's short when a tier has many seasons and long when it has few. "
        "If two tiers' lines barely overlap, the gap is probably real; if they overlap a lot, it could be "
        "luck. The same player appears in many seasons, so the real uncertainty is a little larger than "
        "shown.",
    )


def table_note(summary: pd.DataFrame) -> str:
    skew = (summary["mean_ts_delta"] - summary["median_ts_delta"]).abs()
    if (skew < 0.005).all():
        key = "Median ≈ mean in every tier → no outlier seasons skewing the averages"
    else:
        tier = summary.loc[skew.idxmax(), "group_tier"]
        key = f"Median differs most from the mean for {TIER_PLURALS[tier]} → a few extreme seasons pull it"
    widest = summary.loc[summary["std_ts_delta"].idxmax()]
    return callout(
        3,
        "The numbers behind the bars",
        "The exact values for each tier.",
        key,
        "<b>N</b>: player-seasons. <b>Mean</b>: the average change (the bar). <b>Median</b>: the middle "
        "season when they're lined up from worst to best. <b>Std dev</b>: how far one season typically "
        f"lands from the average, about {widest.std_ts_delta * 100:.1f} points for "
        f"{TIER_PLURALS[widest.group_tier]}, which is why one season says little and averages say more. "
        "<b>Mean usg_delta</b>: the usage change in note 4.",
    )


def usage_note(summary: pd.DataFrame) -> str:
    key = " · ".join(
        f"{TIER_PLURALS[row.group_tier]} {_short(row.mean_usg_delta)}"
        for row in summary.itertuples()
    )
    return callout(
        4,
        "Who gets the ball",
        "Usage is the share of plays a player finishes while he's on the floor. This is how it changes "
        "in the clutch.",
        key,
        "Positive means he runs more of the offense when it's close, negative means less. Read it next to "
        "the scoreboard: usage says who gets the ball, the scoreboard says how well they shoot it.",
    )


def trend_note(
    by_season: pd.DataFrame, summary: pd.DataFrame, min_per_season: int
) -> str:
    key = ""
    wide = by_season.pivot(
        index="season", columns="group_tier", values="mean_ts_delta"
    ).dropna()
    if len(summary) > 1 and len(wide.columns) == len(summary) and len(wide):
        worst = summary.loc[summary["mean_ts_delta"].idxmin(), "group_tier"]
        lowest = int((wide.idxmin(axis=1) == worst).sum())
        key = f"{TIER_PLURALS[worst]} are the lowest line in {lowest} of {len(wide)} seasons"
    return callout(
        5,
        "Season by season",
        "One point per tier per season. Look for which line is <i>usually</i> lowest, not single jumps.",
        key,
        f"A tier only gets a point when it has at least {min_per_season} player-seasons that year. Single "
        "seasons are small samples, so their ups and downs are mostly noise.",
    )


GUIDE_INTRO = """
### What this dashboard asks

Do players with a star reputation really shoot better when the game is close? Every qualifying NBA
player-season from 2004-05 on is compared with **itself**: how the player shot in clutch minutes against how he shot
over the whole season. Players are grouped into three tiers by reputation, and the tiers are compared.

**Start on the Overview** and switch on *Explain this page*: each part of the page gets a numbered note.
"""

GUIDE_FILTERS = """
### Using the filters

The sidebar filters apply to every tab except Player explorer and Ask the data, so the whole dashboard
always describes the same data.

- **Seasons:** limit the data to a range of seasons, for example to check whether the result holds in the
  last ten years.
- **Tiers:** show or hide a tier. Hiding one also hides it from the shot charts and leaderboards.
- **Minimum clutch shot attempts:** drop player-seasons with only a few clutch shots. Those seasons are
  very noisy (one hot night can make them look great), so raising this to 20 or 30 is the best way to
  check whether a finding is real. The *Why the minimum matters* chart on Leaderboards shows why.
- **Reset filters:** back to everything. **Reload data:** use after a new pipeline run.
  **Download filtered data:** the player-seasons you're looking at, as a CSV.
"""

GUIDE_TABS = """
### What each tab shows

- **Overview:** the answer. The average clutch change for each tier, whether the gap is bigger than luck,
  how usage changes, and the season-by-season trend.
- **Leaderboards:** the player-seasons that changed the most in either direction. Raise the minimum clutch
  shot attempts first, or the list is mostly tiny samples.
- **Player explorer:** one player's whole career, full season against clutch, with each season coloured by
  his tier that year.
- **Shot chart:** where clutch shots come from and how they fall. With one player picked you can compare a
  season with the league, with all his other seasons, or with one other season (shown as court zones,
  because one season has too few shots per spot).
- **Ask the data:** ask a question in plain English. Claude writes and runs the SQL, and every query is
  shown under the answer.
"""


def render_guide_tab(st) -> None:
    """The Guide tab: what the dashboard asks, the filters, the tabs, and the full glossary."""
    st.markdown(GUIDE_INTRO)
    st.markdown(GUIDE_FILTERS)
    st.markdown(GUIDE_TABS)
    st.markdown("### Glossary")
    st.markdown(glossary_markdown())
