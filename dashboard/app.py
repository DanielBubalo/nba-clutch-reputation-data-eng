"""NBA Clutch Reputation dashboard.

Run from the project root:
    streamlit run dashboard/app.py
"""

import math
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from court import draw_court
from style import (
    CSS,
    HOT_COLD,
    LINE,
    MUTED,
    PLOTLY_CONFIG,
    TEXT,
    TIER_COLOURS,
    TIER_ORDER,
    TIER_PLURALS,
    scoreboard_html,
)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nba_clutch.duckdb"
REPO_URL = "https://github.com/DanielBubalo/nba-clutch-reputation-data-eng"

MIN_TIER_SEASON = 10  # a tier needs this many player-seasons in a season to get a point on the trend chart
MAX_SCATTER_POINTS = 5_000
BIN_SIZE = 25  # tenths of a foot, so 2.5 ft squares
MIN_BIN_ATTEMPTS = 20

st.set_page_config(page_title="NBA Clutch Reputation", page_icon="🏀", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ data


@st.cache_data(show_spinner="Loading player-seasons…")
def load_player_seasons() -> pd.DataFrame:
    """Every qualifying player-season. Small enough (about 5,000 rows) to load once and filter in memory."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute("""
            SELECT player_id, player_name, season, group_tier, team_abv,
                   ts_season, ts_clutch, ts_delta, usg_delta,
                   fga_clutch, games_played_clutch
            FROM player_clutch_performance
            """).df()


@st.cache_data(show_spinner="Loading clutch shots…")
def load_shots() -> pd.DataFrame:
    """Every clutch shot with a recorded location (a handful have none)."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute("""
            SELECT player_id, player_name, season, group_tier, loc_x, loc_y, shot_made_flag
            FROM shots_with_opponent
            WHERE loc_x IS NOT NULL AND loc_y IS NOT NULL
            """).df()


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


def accuracy_grid(shots: pd.DataFrame) -> pd.DataFrame:
    """Field goal % in 2.5 ft squares, keeping only squares with enough attempts to mean something."""
    binned = shots.assign(
        x_bin=(shots["loc_x"] // BIN_SIZE) * BIN_SIZE + BIN_SIZE / 2,
        y_bin=(shots["loc_y"] // BIN_SIZE) * BIN_SIZE + BIN_SIZE / 2,
    )
    grid = (
        binned.groupby(["x_bin", "y_bin"])["shot_made_flag"]
        .agg(attempts="size", fg_pct="mean")
        .reset_index()
    )
    return grid[grid["attempts"] >= MIN_BIN_ATTEMPTS]


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
    )
    tiers = st.multiselect(
        "Tiers", TIER_ORDER, default=FILTER_DEFAULTS["f_tiers"], key="f_tiers"
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
    if reset_col.button("Reset filters", width="stretch"):
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
    )

    with st.expander("How to read this"):
        st.markdown(
            "**Clutch:** the last 5 minutes of the 4th quarter or overtime, with the score within 5 points "
            "(the NBA's official definition).\n\n"
            "**True shooting (TS%):** scoring efficiency that counts threes and free throws, not just "
            "field goals.\n\n"
            "**ts_delta:** clutch TS% minus full-season TS%. Negative means the player shot worse in the "
            "clutch. Shown in percentage points on the scoreboard.\n\n"
            "**Usage:** the share of a team's possessions a player finishes while on the floor.\n\n"
            "**Tiers:** Star means the player won a star-level NBA award before that season. Olympic "
            "Gold Medalist means a star-level NBA award plus an Olympic gold. Everyone else is Role. "
            "Awards only count from the season after they're won.\n\n"
            "**Qualifying player-season:** at least 15 clutch games and more than 100 season field goal "
            "attempts."
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

overview_tab, leaderboard_tab, player_tab, shots_tab = st.tabs(
    ["Overview", "Leaderboards", "Player explorer", "Shot chart"]
)


# -------------------------------------------------------------- overview

with overview_tab:
    summary = tier_summary(filtered)
    st.markdown(scoreboard_html(summary), unsafe_allow_html=True)

    worst = summary.loc[summary["mean_ts_delta"].idxmin()]
    everyone_declines = (summary["mean_ts_delta"] < 0).all()
    lead = "Every tier shoots worse in the clutch, and " if everyone_declines else ""
    st.markdown(
        f"**{lead}{TIER_PLURALS[worst.group_tier]} drop the most.** "
        "Numbers are the mean change in true shooting from the full season to the clutch, "
        "in percentage points."
    )

    chart_col, table_col = st.columns([3, 2])
    with chart_col:
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
                "std_ts_delta": st.column_config.NumberColumn("Std dev", format="%.3f"),
                "mean_usg_delta": st.column_config.NumberColumn(
                    "Mean usg_delta", format="%+.4f"
                ),
            },
        )
        st.markdown(
            f"**Usage tells the how.** {TIER_PLURALS[worst.group_tier]} change their usage by "
            f"{worst.mean_usg_delta * 100:+.1f} points in the clutch. A positive number means they take "
            "on more of the offense even as their efficiency falls."
        )

    st.subheader("Season by season")
    by_season = (
        filtered.groupby(["season", "group_tier"])["ts_delta"]
        .agg(n="size", mean_ts_delta="mean")
        .reset_index()
    )
    by_season = by_season[by_season["n"] >= MIN_TIER_SEASON]
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
        legend=dict(
            orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right", title=None
        )
    )
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
        "Show", ["Biggest declines", "Biggest improvements"], horizontal=True
    )
    top_n = option_2.slider("Rows", min_value=5, max_value=50, value=15, step=5)

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
        help="Only qualifying seasons appear: 15+ clutch games and 100+ season field goal attempts.",
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

with shots_tab:
    shots_df = load_shots()
    # Keep only shots from the player-seasons the sidebar currently selects.
    selected = shots_df.merge(
        filtered[["player_id", "season"]].drop_duplicates(), on=["player_id", "season"]
    )

    option_1, option_2 = st.columns(2)
    view = option_1.radio(
        "View", ["Accuracy heatmap", "Makes and misses"], horizontal=True
    )
    shooter_options = ["All players"] + sorted(selected["player_name"].unique())
    shooter = option_2.selectbox("Player", shooter_options, key="shooter")
    if shooter != "All players":
        selected = selected[selected["player_name"] == shooter]

    if selected.empty:
        st.warning("No shots match these filters.")
    else:
        shot_1, shot_2, shot_3 = st.columns(3)
        shot_1.metric("Clutch shots", f"{len(selected):,}")
        shot_2.metric("Made", f"{int(selected['shot_made_flag'].sum()):,}")
        shot_3.metric("Field goal %", f"{selected['shot_made_flag'].mean():.1%}")

        if view == "Accuracy heatmap":
            grid = accuracy_grid(selected)
            fg_matrix = grid.pivot(index="y_bin", columns="x_bin", values="fg_pct")
            attempts_matrix = grid.pivot(
                index="y_bin", columns="x_bin", values="attempts"
            )
            fig = go.Figure(
                go.Heatmap(
                    x=fg_matrix.columns,
                    y=fg_matrix.index,
                    z=fg_matrix.values,
                    customdata=attempts_matrix.values,
                    colorscale=HOT_COLD,
                    zmin=0.25,
                    zmax=0.65,
                    colorbar=dict(title="FG%", tickformat=".0%"),
                    hovertemplate="FG%: %{z:.1%}<br>Attempts: %{customdata}<extra></extra>",
                    xgap=1,
                    ygap=1,
                )
            )
            fig.update_layout(title="Clutch field goal % by location")
            st.plotly_chart(
                draw_court(fig), width="stretch", theme=None, config=PLOTLY_CONFIG
            )
            st.caption(
                f"Each square is 2.5 × 2.5 ft. Squares with fewer than {MIN_BIN_ATTEMPTS} attempts are "
                "hidden, for the same reason as the shot minimum: small samples are noise."
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
            fig.update_layout(title="Clutch makes and misses")
            st.plotly_chart(
                draw_court(fig), width="stretch", theme=None, config=PLOTLY_CONFIG
            )
