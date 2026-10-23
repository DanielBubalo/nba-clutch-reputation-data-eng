"""NBA Clutch Reputation dashboard.

Run from the project root:
    streamlit run dashboard/app.py
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from court import draw_court
from hexbin import glowing_chart_html, hex_stats, hexbin_figure
from zones import zone_chart_html, zone_counts, zone_figure, zone_stats
from guide import (
    GUIDE_CSS,
    SIDEBAR_TERMS,
    chart_hint,
    chart_note,
    glossary_markdown,
    render_guide_tab,
    scoreboard_note,
    start_note,
    table_note,
    trend_note,
    usage_note,
)
from style import (
    CSS,
    HOT_COLD,
    LINE,
    MUTED,
    NAVY,
    PLOTLY_CONFIG,
    TEXT,
    TIER_COLOURS,
    TIER_ORDER,
    TIER_PLURALS,
    scoreboard_html,
)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nba_clutch.duckdb"
sys.path.insert(
    0, str(ROOT)
)  # the agent package lives at the project root, next to dashboard/
from agent import analyst  # noqa: E402

REPO_URL = "https://github.com/DanielBubalo/nba-clutch-reputation-data-eng"

MIN_TIER_SEASON = 10  # a tier needs this many player-seasons in a season to get a point on the trend chart
MAX_SCATTER_POINTS = 5_000

st.set_page_config(page_title="NBA Clutch Reputation", page_icon="🏀", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(GUIDE_CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ data


@st.cache_data(show_spinner="Loading player-seasons…")
def load_player_seasons() -> pd.DataFrame:
    """Every qualifying player-season. Small enough (about 5,000 rows) to load once and filter in memory."""
    with analyst.connect() as con:
        return con.execute("""
            SELECT player_id, player_name, season, group_tier, team_abv,
                   ts_season, ts_clutch, ts_delta, usg_delta,
                   fga_clutch, games_played_clutch
            FROM player_clutch_performance
            """).df()


@st.cache_data(show_spinner="Loading clutch shots…")
def load_shots() -> pd.DataFrame:
    """Every clutch shot with a recorded location (a handful have none)."""
    with analyst.connect() as con:
        return con.execute("""
            SELECT player_id, player_name, season, group_tier, loc_x, loc_y, shot_made_flag
            FROM shots_with_opponent
            WHERE loc_x IS NOT NULL AND loc_y IS NOT NULL
            """).df()


@st.cache_data(show_spinner=False)
def load_league_zones() -> pd.DataFrame:
    """Attempts and makes per court zone for every clutch shot: the zone chart's league baseline."""
    return zone_counts(load_shots())


def tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    """The Findings table: one row per tier, plus a 95% interval for the mean."""
    summary = (
        df.groupby("group_tier")
        .agg(
            n=("ts_delta", "size"),
            mean_ts_delta=("ts_delta", "mean"),
            median_ts_delta=("ts_delta", "median"),
            std_ts_delta=("ts_delta", "std"),
            mean_usg_delta=("usg_delta", "mean"),
        )
        .reindex(TIER_ORDER)
        .dropna(subset=["n"])
        .reset_index()
    )
    summary["ci95"] = 1.96 * summary["std_ts_delta"] / summary["n"].map(math.sqrt)
    return summary


if not DB_PATH.exists():
    st.error(
        f"No database at `{DB_PATH}`. Run the pipeline first (see the README), "
        "then reload this page."
    )
    st.stop()

try:
    seasons_df = load_player_seasons()
except duckdb.IOException:
    st.error(
        "The database is locked, probably because the pipeline or a dbt build is writing to it. "
        "Wait for it to finish, then reload."
    )
    st.stop()

ALL_SEASONS = sorted(seasons_df["season"].unique())
FILTER_DEFAULTS = {
    "f_seasons": (ALL_SEASONS[0], ALL_SEASONS[-1]),
    "f_tiers": TIER_ORDER,
    "f_min_fga": 0,
}


# --------------------------------------------------------------- sidebar
# Filters here apply to every tab, so the whole dashboard always describes the same data.


with st.sidebar:
    st.markdown(
        '<div class="brand">NBA Clutch Reputation</div>'
        '<div class="brand-sub">Do Stars really perform better in the clutch, '
        "or does reputation outpace results?</div>",
        unsafe_allow_html=True,
    )

    st.subheader("Filters")
    first_season, last_season = st.select_slider(
        "Seasons",
        options=ALL_SEASONS,
        value=FILTER_DEFAULTS["f_seasons"],
        key="f_seasons",
        help="Only include seasons in this range. Applies to every tab except Player explorer "
        "and Ask the data.",
    )
    tiers = st.multiselect(
        "Tiers",
        TIER_ORDER,
        default=FILTER_DEFAULTS["f_tiers"],
        key="f_tiers",
        help="Which reputation tiers to include. Star: a star-level NBA award before that season. "
        "Olympic Gold Medalist: that plus an Olympic gold. Role: everyone else.",
    )
    min_fga = st.slider(
        "Minimum clutch shot attempts",
        min_value=0,
        max_value=100,
        value=FILTER_DEFAULTS["f_min_fga"],
        key="f_min_fga",
        help="Player-seasons qualify with 15+ clutch games, but some take very few clutch shots. "
        "Raise this to see whether the findings hold without small samples.",
    )

    in_scope = seasons_df[
        seasons_df["group_tier"].isin(tiers)
        & seasons_df["season"].between(first_season, last_season)
    ]
    filtered = in_scope[in_scope["fga_clutch"] >= min_fga]

    st.progress(
        len(filtered) / len(seasons_df),
        text=f"{len(filtered):,} of {len(seasons_df):,} player-seasons",
    )

    reset_col, reload_col = st.columns(2)
    if reset_col.button(
        "Reset filters",
        width="stretch",
        help="Put every filter back to its default: all seasons, all tiers, no shot minimum.",
    ):
        for key in FILTER_DEFAULTS:
            st.session_state.pop(key, None)
        st.rerun()
    if reload_col.button(
        "Reload data", width="stretch", help="Clear the cache after a new pipeline run."
    ):
        st.cache_data.clear()
        st.rerun()

    st.download_button(
        "Download filtered data (CSV)",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="clutch_player_seasons.csv",
        mime="text/csv",
        width="stretch",
        help="Download the player-seasons the filters currently select, as a CSV.",
    )

    with st.expander("How to read this"):
        st.markdown(
            glossary_markdown(SIDEBAR_TERMS)
            + "\n\nThe **Guide** tab explains every filter and tab, with the full glossary."
        )

    built = datetime.fromtimestamp(DB_PATH.stat().st_mtime)
    st.caption(
        f"Data: nba_api, regular seasons {ALL_SEASONS[0]} to {ALL_SEASONS[-1]}. "
        f"Database last built {built:%b %d, %Y at %H:%M}. "
        f"[Source code and method]({REPO_URL})"
    )


# ---------------------------------------------------------------- header

st.title("🏀 Does clutch reputation match clutch results?")

if filtered.empty:
    st.warning(
        "No player-seasons match the sidebar filters. Widen them, or press Reset filters."
    )
    st.stop()

overview_tab, leaderboard_tab, player_tab, shots_tab, ask_tab, guide_tab = st.tabs(
    [
        "Overview",
        "Leaderboards",
        "Player explorer",
        "Shot chart",
        "Ask the data",
        "Guide",
    ]
)


# -------------------------------------------------------------- overview

with overview_tab:
    summary = tier_summary(filtered)
    explain = st.toggle(
        "Explain this page",
        key="explain_overview",
        help="Puts each part of the page in a numbered box with a short note on how to read it.",
    )

    def part(step: int):
        """A box for one explained part of the page: bordered only while Explain this page is on."""
        return st.container(border=explain, key=f"guide-{step}")

    if explain:
        st.markdown(start_note(summary), unsafe_allow_html=True)

    with part(1):
        if explain:
            st.markdown(scoreboard_note(summary), unsafe_allow_html=True)
        st.markdown(scoreboard_html(summary), unsafe_allow_html=True)

        worst = summary.loc[summary["mean_ts_delta"].idxmin()]
        everyone_declines = (summary["mean_ts_delta"] < 0).all()
        lead = (
            "Every tier shoots worse in the clutch, and " if everyone_declines else ""
        )
        st.markdown(
            f"**{lead}{TIER_PLURALS[worst.group_tier]} drop the most.** "
            "Numbers are the mean change in true shooting from the full season to the clutch, "
            "in percentage points."
        )

    chart_col, table_col = st.columns([3, 2])
    with chart_col, part(2):
        if explain:
            st.markdown(chart_note(summary), unsafe_allow_html=True)
        fig = px.bar(
            summary,
            x="group_tier",
            y="mean_ts_delta",
            error_y="ci95",
            color="group_tier",
            color_discrete_map=TIER_COLOURS,
            labels={
                "group_tier": "Tier",
                "mean_ts_delta": "Mean ts_delta (clutch − season)",
            },
            title="Mean clutch change in true shooting, with 95% intervals",
        )
        fig.update_layout(showlegend=False)
        fig.update_traces(error_y=dict(color=MUTED, thickness=1.5))
        fig.add_hline(y=0, line_color=LINE, line_width=1)
        st.plotly_chart(fig, width="stretch", theme=None, config=PLOTLY_CONFIG)
        st.caption(
            "Error bars are ±1.96 standard errors. The same player appears in many seasons, "
            "so the real uncertainty is somewhat larger than shown."
        )

    with table_col:
        with part(3):
            if explain:
                st.markdown(table_note(summary), unsafe_allow_html=True)
            st.subheader("Findings by tier")
            st.dataframe(
                summary.drop(columns="ci95"),
                hide_index=True,
                width="stretch",
                column_config={
                    "group_tier": "Tier",
                    "n": st.column_config.NumberColumn("N", format="%d"),
                    "mean_ts_delta": st.column_config.NumberColumn(
                        "Mean ts_delta", format="%.4f"
                    ),
                    "median_ts_delta": st.column_config.NumberColumn(
                        "Median", format="%.3f"
                    ),
                    "std_ts_delta": st.column_config.NumberColumn(
                        "Std dev", format="%.3f"
                    ),
                    "mean_usg_delta": st.column_config.NumberColumn(
                        "Mean usg_delta", format="%+.4f"
                    ),
                },
            )
        with part(4):
            if explain:
                st.markdown(usage_note(summary), unsafe_allow_html=True)
            st.markdown(
                f"**Usage tells the how.** {TIER_PLURALS[worst.group_tier]} change their usage by "
                f"{worst.mean_usg_delta * 100:+.1f} points in the clutch. A positive number means they take "
                "on more of the offense even as their efficiency falls."
            )

    by_season = (
        filtered.groupby(["season", "group_tier"])["ts_delta"]
        .agg(n="size", mean_ts_delta="mean")
        .reset_index()
    )
    by_season = by_season[by_season["n"] >= MIN_TIER_SEASON]
    with part(5):
        if explain:
            st.markdown(
                trend_note(by_season, summary, MIN_TIER_SEASON), unsafe_allow_html=True
            )
        st.subheader("Season by season")
        trend = px.line(
            by_season,
            x="season",
            y="mean_ts_delta",
            color="group_tier",
            color_discrete_map=TIER_COLOURS,
            category_orders={"group_tier": TIER_ORDER, "season": ALL_SEASONS},
            markers=True,
            hover_data={"n": True},
            labels={
                "season": "Season",
                "mean_ts_delta": "Mean ts_delta",
                "group_tier": "Tier",
                "n": "Player-seasons",
            },
            title="Mean clutch change in true shooting, by season",
        )
        trend.add_hline(y=0, line_color=LINE, line_width=1)
        trend.update_layout(
            xaxis_type="category",  # seasons like "2004-05" otherwise get read as dates
            legend=dict(
                orientation="h",
                y=1.02,
                yanchor="bottom",
                x=1,
                xanchor="right",
                title=None,
            ),
        )
        st.markdown(chart_hint("a tier"), unsafe_allow_html=True)
        st.plotly_chart(trend, width="stretch", theme=None, config=PLOTLY_CONFIG)
        st.caption(
            f"A tier only gets a point in seasons where it has at least {MIN_TIER_SEASON} player-seasons, "
            "so single seasons with tiny groups don't swing the line. Year-to-year jumps are mostly noise; "
            "look for whether one tier sits below the others most seasons."
        )


# ---------------------------------------------------------- leaderboards

with leaderboard_tab:
    st.subheader("Biggest clutch swings")
    option_1, option_2 = st.columns(2)
    direction = option_1.radio(
        "Show",
        ["Biggest declines", "Biggest improvements"],
        horizontal=True,
        help="Biggest declines: player-seasons that shot much worse in the clutch than over the "
        "season. Biggest improvements: much better. Each row is one player in one season.",
    )
    top_n = option_2.slider(
        "Rows",
        min_value=5,
        max_value=50,
        value=15,
        step=5,
        help="How many player-seasons to list.",
    )

    if min_fga < 20:
        st.caption(
            "Tip: raise the minimum clutch shot attempts in the sidebar. At low minimums the extremes "
            "are dominated by player-seasons with only a handful of clutch shots."
        )

    leaders = filtered.sort_values(
        "ts_delta", ascending=direction == "Biggest declines"
    ).head(top_n)
    st.dataframe(
        leaders[
            [
                "player_name",
                "season",
                "group_tier",
                "team_abv",
                "ts_season",
                "ts_clutch",
                "ts_delta",
                "fga_clutch",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "player_name": "Player",
            "season": "Season",
            "group_tier": "Tier",
            "team_abv": "Team",
            "ts_season": st.column_config.NumberColumn("Season TS%", format="%.3f"),
            "ts_clutch": st.column_config.NumberColumn("Clutch TS%", format="%.3f"),
            "ts_delta": st.column_config.NumberColumn("Change", format="%+.3f"),
            "fga_clutch": st.column_config.NumberColumn("Clutch FGA", format="%d"),
        },
    )

    st.subheader("Why the minimum matters")
    scatter = px.scatter(
        in_scope,
        x="fga_clutch",
        y="ts_delta",
        color="group_tier",
        color_discrete_map=TIER_COLOURS,
        category_orders={"group_tier": TIER_ORDER},
        hover_data=["player_name", "season"],
        log_x=True,
        opacity=0.5,
        labels={
            "fga_clutch": "Clutch shot attempts (log scale)",
            "ts_delta": "ts_delta",
            "group_tier": "Tier",
        },
    )
    scatter.add_vline(x=max(min_fga, 1), line_dash="dash", line_color=MUTED)
    scatter.add_hline(y=0, line_color=LINE, line_width=1)
    st.markdown(chart_hint("a tier"), unsafe_allow_html=True)
    st.plotly_chart(scatter, width="stretch", theme=None, config=PLOTLY_CONFIG)
    st.caption(
        "Player-seasons with few clutch shots spread far above and below zero; the spread narrows "
        "as attempts grow. The dashed line is the sidebar minimum: points left of it are excluded."
    )


# ------------------------------------------------------- player explorer

with player_tab:
    st.caption("A player's whole career, so the sidebar filters don't apply here.")
    players = (
        seasons_df.groupby(["player_id", "player_name"])
        .size()
        .reset_index(name="seasons")
        .sort_values("player_name")
    )
    labels = {
        row.player_id: f"{row.player_name} ({row.seasons} season{'s' if row.seasons != 1 else ''})"
        for row in players.itertuples()
    }
    default_ids = players.loc[players["player_name"] == "LeBron James", "player_id"]
    default_index = (
        int(players["player_id"].tolist().index(default_ids.iloc[0]))
        if len(default_ids)
        else 0
    )
    player_id = st.selectbox(
        "Player",
        players["player_id"].tolist(),
        index=default_index,
        format_func=labels.get,
        help="Only qualifying seasons appear: 15+ clutch games and more than 100 season field goal attempts.",
    )

    career = seasons_df[seasons_df["player_id"] == player_id].sort_values("season")
    name = career["player_name"].iloc[0]

    stat_1, stat_2, stat_3, stat_4 = st.columns(4)
    stat_1.metric("Qualifying seasons", len(career))
    stat_2.metric("Average ts_delta", f"{career['ts_delta'].mean():+.3f}")
    stat_3.metric("Total clutch FGA", f"{int(career['fga_clutch'].sum()):,}")
    star_seasons = career[career["group_tier"] != "Role"]
    stat_4.metric(
        "First Star/Olympic season",
        star_seasons["season"].iloc[0] if len(star_seasons) else "None",
    )

    st.markdown(chart_hint("a line"), unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=career["season"],
            y=career["ts_season"],
            name="Full season",
            mode="lines+markers",
            line=dict(color=MUTED, width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=career["season"],
            y=career["ts_clutch"],
            name="Clutch",
            mode="lines+markers",
            line=dict(color=TEXT, width=2, dash="dot"),
            marker=dict(
                size=11,
                color=career["group_tier"].map(TIER_COLOURS),
                line=dict(color=TEXT, width=1),
            ),
            customdata=career[["group_tier", "fga_clutch", "ts_delta"]],
            hovertemplate=(
                "%{x}<br>Clutch TS%: %{y:.3f}<br>Tier: %{customdata[0]}"
                "<br>Clutch FGA: %{customdata[1]}<br>Change: %{customdata[2]:+.3f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"{name}: true shooting, full season vs. clutch",
        yaxis_title="True shooting %",
        xaxis_title="Season",
        xaxis_type="category",  # seasons like "2004-05" otherwise get read as dates
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch", theme=None, config=PLOTLY_CONFIG)
    st.caption(
        "Clutch markers are coloured by that season's tier: blue = Role, gold = Olympic Gold Medalist, "
        "orange = Star. Tiers only count awards won before the season, so you can see when a player's "
        "reputation starts."
    )

    st.dataframe(
        career[
            [
                "season",
                "team_abv",
                "group_tier",
                "ts_season",
                "ts_clutch",
                "ts_delta",
                "usg_delta",
                "fga_clutch",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "season": "Season",
            "team_abv": "Team",
            "group_tier": "Tier",
            "ts_season": st.column_config.NumberColumn("Season TS%", format="%.3f"),
            "ts_clutch": st.column_config.NumberColumn("Clutch TS%", format="%.3f"),
            "ts_delta": st.column_config.NumberColumn("Change", format="%+.3f"),
            "usg_delta": st.column_config.NumberColumn("Usage change", format="%+.3f"),
            "fga_clutch": st.column_config.NumberColumn("Clutch FGA", format="%d"),
        },
    )


# ------------------------------------------------------------ shot chart


@st.fragment
def shot_chart_tab(filtered: pd.DataFrame) -> None:
    """The Shot chart tab. A fragment, so its own controls rerun only this tab, not the whole page."""
    shots_df = load_shots()
    # Keep only shots from the player-seasons the sidebar currently selects.
    selected = shots_df.merge(
        filtered[["player_id", "season"]].drop_duplicates(), on=["player_id", "season"]
    )

    option_1, option_2 = st.columns(2)
    view = option_1.radio(
        "View",
        ["Shot chart", "Makes and misses"],
        horizontal=True,
        help="Shot chart: hexagons sized by how many shots came from each spot and coloured by "
        "how well they fell. Makes and misses: every shot as its own dot.",
    )
    shooter_options = ["All players"] + sorted(selected["player_name"].unique())
    shooter = option_2.selectbox(
        "Player",
        shooter_options,
        key="shooter",
        help="Pick one player to compare his seasons, or keep All players for everyone the "
        "sidebar selects.",
    )
    if shooter != "All players":
        selected = selected[selected["player_name"] == shooter]

    # One player's shot chart can be compared with the league, all his other seasons, or one other season.
    baseline, baseline_label, compare_season, vs_text = (
        shots_df,
        "League",
        None,
        "the league",
    )
    if view == "Shot chart" and shooter != "All players" and not selected.empty:
        player_seasons = sorted(selected["season"].unique(), reverse=True)
        option_3, option_4, option_5 = st.columns([2, 1, 1])
        compare = option_3.radio(
            "Compare with",
            ["League", "Other seasons", "One season"],
            horizontal=True,
            help="Other seasons: one season against all of this player's other seasons in the sidebar range. "
            "One season: one season against another single season.",
        )
        if compare != "League":
            if len(player_seasons) < 2:
                option_4.info(
                    "Only one of this player's seasons is in the sidebar range, so there's nothing to "
                    "compare with. Showing the league comparison instead."
                )
            else:
                compare_season = option_4.selectbox(
                    "Season",
                    player_seasons,
                    help="The season to show on the court.",
                )
                others = selected[selected["season"] != compare_season]
                if compare == "Other seasons":
                    baseline, baseline_label, vs_text = (
                        others,
                        "Other seasons",
                        "other seasons",
                    )
                else:
                    versus = option_5.selectbox(
                        "Compared with",
                        [
                            season
                            for season in player_seasons
                            if season != compare_season
                        ],
                        help="The season to compare it with, zone by zone.",
                    )
                    baseline, baseline_label, vs_text = (
                        others[others["season"] == versus],
                        versus,
                        versus,
                    )
                selected = selected[selected["season"] == compare_season]

    if selected.empty:
        st.warning("No shots match these filters.")
    else:
        fg_pct = selected["shot_made_flag"].mean()
        fg_delta = None
        if compare_season:
            fg_delta = f"{(fg_pct - baseline['shot_made_flag'].mean()) * 100:+.1f} pts vs {vs_text}"
        shot_1, shot_2, shot_3 = st.columns(3)
        shot_1.metric("Clutch shots", f"{len(selected):,}")
        shot_2.metric("Made", f"{int(selected['shot_made_flag'].sum()):,}")
        shot_3.metric("Field goal %", f"{fg_pct:.1%}", delta=fg_delta)

        if view == "Shot chart" and compare_season:
            # One season's hexagons are mostly 0 to 2 shots, so seasons are compared zone by zone.
            stats = zone_stats(selected, baseline, load_league_zones())
            fig, order, hot = zone_figure(stats, HOT_COLD, baseline_label, NAVY)
            fig.update_layout(
                title=f"{shooter}, {compare_season}: clutch shots vs. {vs_text}"
            )
            # Its own small page, like the hexagons, so the zones can animate in and hot zones pulse.
            st.iframe(
                zone_chart_html(
                    draw_court(fig), order, hot, PLOTLY_CONFIG, NAVY, height=620
                ),
                height=640,
            )
            st.dataframe(
                stats[
                    [
                        "zone",
                        "makes",
                        "attempts",
                        "fg",
                        "share",
                        "base_makes",
                        "base_attempts",
                        "base_fg_raw",
                        "base_share",
                    ]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "zone": "Zone",
                    "makes": st.column_config.NumberColumn(
                        f"{compare_season} made", format="%d"
                    ),
                    "attempts": st.column_config.NumberColumn(
                        f"{compare_season} shots", format="%d"
                    ),
                    "fg": st.column_config.NumberColumn(
                        f"{compare_season} FG%", format="percent"
                    ),
                    "share": st.column_config.NumberColumn(
                        "Share of his shots", format="percent"
                    ),
                    "base_makes": st.column_config.NumberColumn(
                        f"{baseline_label} made", format="%d"
                    ),
                    "base_attempts": st.column_config.NumberColumn(
                        f"{baseline_label} shots", format="%d"
                    ),
                    "base_fg_raw": st.column_config.NumberColumn(
                        f"{baseline_label} FG%", format="percent"
                    ),
                    "base_share": st.column_config.NumberColumn(
                        f"{baseline_label} share", format="percent"
                    ),
                },
            )
            compared_with = (
                f"{shooter}'s other seasons in the sidebar range"
                if baseline_label == "Other seasons"
                else f"{shooter}'s {vs_text} season"
            )
            st.caption(
                f"Each zone compares {compare_season} with {compared_with}: orange is better, blue worse. "
                "Labels show field goal % for both, then this season's makes and attempts; share of shots shows "
                "where he shot from. Colour is adjusted the same way as the hexagons: a zone with only a few shots "
                "is pulled toward the comparison, and the comparison toward the league, so a lucky streak can't "
                "paint it hot. Corner threes are in the table and the hover."
            )
        elif view == "Shot chart":
            # Comparing the whole league with itself would colour everything "even", so then show raw FG%.
            relative = len(selected) < len(shots_df)
            stats = hex_stats(selected, shots_df)
            fig, glow = hexbin_figure(stats, HOT_COLD, relative)
            fig.update_layout(
                title="Clutch shots: where they come from and how they fall"
            )
            # Rendered as its own small page so the glow can run on its own, with no play button.
            st.iframe(
                glowing_chart_html(
                    draw_court(fig), glow, PLOTLY_CONFIG, NAVY, height=620
                ),
                height=640,
            )
            if relative:
                st.caption(
                    "Bigger hexagons mean more shots from that spot. Colour compares field goal % with every "
                    "clutch shot from the same spot, 2004-05 to 2025-26: orange is better than the league, blue "
                    "worse. Spots with few shots are pulled toward the league average, so one lucky make can't "
                    "paint a hot zone."
                )
            else:
                st.caption(
                    "Bigger hexagons mean more shots from that spot; colour is field goal %. Pick a player or "
                    "narrow the sidebar filters to compare them with the league from each spot."
                )
        else:
            sample = selected
            if len(selected) > MAX_SCATTER_POINTS:
                sample = selected.sample(MAX_SCATTER_POINTS, random_state=0)
                st.caption(
                    f"Showing a random {MAX_SCATTER_POINTS:,} of {len(selected):,} shots so the chart stays fast. "
                    "Pick a player or narrow the seasons to see every shot."
                )
            fig = go.Figure()
            for made, label, colour, symbol in [
                (0, "Miss", "#2F6DB5", "x"),
                (1, "Make", "#FF5A36", "circle"),
            ]:
                part = sample[sample["shot_made_flag"] == made]
                fig.add_trace(
                    go.Scatter(
                        x=part["loc_x"],
                        y=part["loc_y"],
                        mode="markers",
                        name=label,
                        marker=dict(color=colour, symbol=symbol, size=6, opacity=0.6),
                        customdata=part[["player_name", "season"]],
                        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
                    )
                )
            st.markdown(chart_hint("Make or Miss", zoom=False), unsafe_allow_html=True)
            fig.update_layout(title="Clutch makes and misses")
            st.plotly_chart(
                draw_court(fig), width="stretch", theme=None, config=PLOTLY_CONFIG
            )


with shots_tab:
    shot_chart_tab(filtered)


# ---------------------------------------------------------- ask the data
# The analyst agent from agent/analyst.py, behind a chat window.

MAX_QUESTION_CHARS = 500
ASK_LOG = (
    ROOT / "agent" / "ask_log.jsonl"
)  # one line per question asked here (gitignored)
MAX_QUESTIONS = 20  # per browser session, so one visitor can't run up the API bill
HISTORY_MESSAGES = (
    6  # the last few messages go along with each question, so follow-ups work
)
EXAMPLE_QUESTIONS = [
    "Do Stars or Role players decline more in the clutch?",
    "Which Stars improved the most in the clutch, with at least 30 clutch shots?",
    "Does LeBron James shoot better or worse in the clutch than in the full season?",
]
CHAT_INSTRUCTIONS = (
    "You are answering inside a dashboard chat. The interface already shows every SQL query you ran, "
    "so do not include a Queries used section or any SQL in your answer. Lead with the direct answer, "
    "then give at most a few short bullets of supporting numbers and caveats."
)


def step_line(step: int, name: str, tool_input: dict, output: str) -> str:
    """One readable line about a tool call, for the live progress box."""
    if name == "describe_models":
        return f"**Step {step}.** Read the table descriptions."
    status = "failed, retrying" if output.startswith("Query failed") else "done"
    return f"**Step {step}.** Ran a query ({status})."


def log_question(question: str, reply: dict, result) -> None:
    """Append one line per question, so questions that went badly can become eval cases.

    result is the AgentResult, or None if Claude couldn't be reached.
    """
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "complete": bool(result and result.complete),
        "stop_reason": result.stop_reason if result else "api_error",
        "steps": result.steps if result else 0,
        "seconds": round(result.seconds, 1) if result else 0,
        "queries": len(reply.get("queries", [])),
        "failed_queries": result.failed_queries if result else 0,
        "answer": reply["content"][:2000],
    }
    try:
        with ASK_LOG.open("a") as log:
            log.write(json.dumps(record) + "\n")
    except OSError:
        pass  # logging must never break the chat


def show_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        queries = message.get("queries", [])
        if queries:
            label = f"How this was answered: {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}"
            with st.expander(f"{label}, {message['seconds']:.0f}s"):
                for query in queries:
                    if not query["ok"]:
                        st.caption("This query failed, and the agent corrected it:")
                    st.code(query["sql"], language="sql")
        if message.get("incomplete"):
            st.warning(
                f"This answer may be incomplete (stop reason: {message['incomplete']})."
            )


with ask_tab:
    st.subheader("Ask the data")
    st.caption(
        "Questions are answered by Claude, which reads the dbt model descriptions and runs SQL against "
        "the database. The connection is read-only, and every number comes from a query you can open "
        "under the answer. The sidebar filters don't apply here: say what you want in the question."
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.info(
            "Set ANTHROPIC_API_KEY in the terminal before starting the dashboard to turn this on "
            "(see Analyst Agent in the README)."
        )
    else:
        chat = st.session_state.setdefault("chat", [])
        conversation = (
            st.container()
        )  # earlier messages, and the new one as it's answered
        with conversation:
            for message in chat:
                show_message(message)

        if not chat:
            st.markdown("**Try one of these:**")
            for column, example in zip(
                st.columns(len(EXAMPLE_QUESTIONS)), EXAMPLE_QUESTIONS
            ):
                if column.button(
                    example,
                    width="stretch",
                    help="Ask this question. Every SQL query used to answer it is shown under the answer.",
                ):
                    st.session_state["example_question"] = example
                    st.rerun()

        asked = sum(message["role"] == "user" for message in chat)
        typed = st.chat_input(
            (
                "Ask about clutch performance…"
                if asked < MAX_QUESTIONS
                else "Question limit reached for this session"
            ),
            max_chars=MAX_QUESTION_CHARS,
            disabled=asked >= MAX_QUESTIONS,
        )
        question = typed or st.session_state.pop("example_question", None)

        if question:
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in chat[-HISTORY_MESSAGES:]
            ]
            queries: list[dict] = []
            result = None
            with conversation:
                show_message({"role": "user", "content": question})
                with st.chat_message("assistant"):
                    with st.status("Thinking…", expanded=True) as progress:

                        def on_step(
                            step: int, name: str, tool_input: dict, output: str
                        ) -> None:
                            if name == "run_sql":
                                queries.append(
                                    {
                                        "sql": tool_input.get("query", ""),
                                        "ok": not output.startswith("Query failed"),
                                    }
                                )
                            progress.update(label=f"Working… step {step}")
                            st.markdown(step_line(step, name, tool_input, output))

                        try:
                            analyst.trace.quiet = (
                                True  # the progress box replaces the terminal trace
                            )
                            result = analyst.ask(
                                question,
                                history=history,
                                on_step=on_step,
                                extra_instructions=CHAT_INSTRUCTIONS,
                            )
                        except anthropic.AnthropicError as error:
                            progress.update(
                                label="Couldn't reach Claude", state="error"
                            )
                            reply = {
                                "role": "assistant",
                                "content": f"Sorry, the question couldn't be answered: {type(error).__name__}.",
                            }
                        else:
                            progress.update(
                                label=f"Answered in {result.steps} steps, {result.seconds:.0f}s",
                                state="complete" if result.complete else "error",
                                expanded=False,
                            )
                            reply = {
                                "role": "assistant",
                                "content": result.answer,
                                "queries": queries,
                                "seconds": result.seconds,
                                "incomplete": (
                                    None if result.complete else result.stop_reason
                                ),
                            }
            log_question(question, reply, result)
            chat.extend([{"role": "user", "content": question}, reply])
            st.rerun()  # redraw the conversation with the finished answer in place

        if chat and st.button(
            "Clear conversation", help="Remove the conversation and start fresh."
        ):
            st.session_state["chat"] = []
            st.rerun()


# ------------------------------------------------------------------ guide


with guide_tab:
    render_guide_tab(st)
