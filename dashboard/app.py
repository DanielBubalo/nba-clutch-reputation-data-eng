"""NBA Clutch Reputation dashboard.

Run from the project root:
    streamlit run dashboard/app.py
"""

import math
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from court import draw_court

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nba_clutch.duckdb"

TIER_ORDER = ["Role", "Olympic Gold Medalist", "Star"]
TIER_PLURALS = {
    "Role": "Role players",
    "Olympic Gold Medalist": "Olympic Gold Medalists",
    "Star": "Stars",
}
TIER_COLOURS = {
    "Role": "#8c9bab",
    "Olympic Gold Medalist": "#e0b14a",
    "Star": "#e4572e",
}

st.set_page_config(page_title="NBA Clutch Reputation", page_icon="🏀", layout="wide")


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


@st.cache_data(show_spinner=False)
def count_shots() -> int:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute("SELECT COUNT(*) FROM shots_with_opponent").fetchone()[0]


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


# ---------------------------------------------------------------- header

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

st.title("🏀 Does clutch reputation match clutch results?")
st.caption(
    "Clutch = last 5 minutes of the 4th quarter or overtime, score within 5 points. "
    "ts_delta = clutch true shooting minus season true shooting, so negative means worse in the clutch."
)

with st.sidebar:
    st.header("About the data")
    st.write(
        f"{len(seasons_df):,} qualifying player-seasons, "
        f"{seasons_df['season'].min()} to {seasons_df['season'].max()}."
    )
    st.write("Built from `player_clutch_performance` in DuckDB, read-only.")
    if st.button("Reload data", help="Clear the cache after a new pipeline run."):
        st.cache_data.clear()
        st.rerun()

overview_tab, leaderboard_tab, player_tab, shots_tab = st.tabs(
    ["Overview", "Leaderboards", "Player explorer", "Shot chart"]
)


# -------------------------------------------------------------- overview

with overview_tab:
    summary = tier_summary(seasons_df)

    kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
    kpi_1.metric("Player-seasons", f"{len(seasons_df):,}")
    kpi_2.metric("Unique players", f"{seasons_df['player_name'].nunique():,}")
    kpi_3.metric("Clutch shots", f"{count_shots():,}")
    kpi_4.metric("Seasons", f"{seasons_df['season'].nunique()}")

    if not summary.empty:
        worst = summary.loc[summary["mean_ts_delta"].idxmin()]
        everyone_declines = (summary["mean_ts_delta"] < 0).all()
        lead = (
            "Every tier shoots worse in the clutch, and " if everyone_declines else ""
        )
        details = ", ".join(
            f"{TIER_PLURALS[row.group_tier]} {row.mean_ts_delta:+.4f}"
            for row in summary.itertuples()
        )
        st.info(
            f"**{lead}{TIER_PLURALS[worst.group_tier]} drop the most.** "
            f"Mean clutch change in true shooting: {details}."
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
        fig.add_hline(y=0, line_color="gray", line_width=1)
        st.plotly_chart(fig, width="stretch")
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


# ---------------------------------------------------------- leaderboards

with leaderboard_tab:
    st.subheader("Biggest clutch swings")

    all_seasons = sorted(seasons_df["season"].unique())
    filter_1, filter_2, filter_3 = st.columns(3)
    with filter_1:
        tiers = st.multiselect("Tiers", TIER_ORDER, default=TIER_ORDER)
        direction = st.radio(
            "Show", ["Biggest declines", "Biggest improvements"], horizontal=True
        )
    with filter_2:
        first_season, last_season = st.select_slider(
            "Seasons", options=all_seasons, value=(all_seasons[0], all_seasons[-1])
        )
        top_n = st.slider("Rows", min_value=5, max_value=50, value=15, step=5)
    with filter_3:
        min_fga = st.slider(
            "Minimum clutch shot attempts",
            min_value=0,
            max_value=int(seasons_df["fga_clutch"].max()),
            value=20,
            help="The pipeline has no minimum on clutch shots, so some player-seasons rest on "
            "very few attempts. Raise this to filter out small-sample noise.",
        )

    in_scope = seasons_df[
        seasons_df["group_tier"].isin(tiers)
        & seasons_df["season"].between(first_season, last_season)
    ]
    filtered = in_scope[in_scope["fga_clutch"] >= min_fga]
    st.caption(
        f"{len(filtered):,} player-seasons match. The shot minimum removed "
        f"{len(in_scope) - len(filtered):,}."
    )

    ascending = direction == "Biggest declines"
    leaders = filtered.sort_values("ts_delta", ascending=ascending).head(top_n)
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
    scatter.add_vline(x=max(min_fga, 1), line_dash="dash", line_color="gray")
    scatter.add_hline(y=0, line_color="gray", line_width=1)
    st.plotly_chart(scatter, width="stretch")
    st.caption(
        "Player-seasons with few clutch shots spread far above and below zero; the spread narrows "
        "as attempts grow. The dashed line is your minimum: points left of it are excluded above."
    )

# ------------------------------------------------------- player explorer

with player_tab:
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
            line=dict(color="#8c9bab", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=career["season"],
            y=career["ts_clutch"],
            name="Clutch",
            mode="lines+markers",
            line=dict(color="#4a4a4a", width=2, dash="dot"),
            marker=dict(
                size=11,
                color=career["group_tier"].map(TIER_COLOURS),
                line=dict(color="white", width=1),
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
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Clutch markers are coloured by that season's tier: grey = Role, gold = Olympic Gold Medalist, "
        "red = Star. Tiers only count awards won before the season, so you can see when a player's "
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

MAX_SCATTER_POINTS = 5_000
BIN_SIZE = 25  # tenths of a foot, so 2.5 ft squares
MIN_BIN_ATTEMPTS = 20


@st.cache_data(show_spinner="Loading clutch shots…")
def load_shots() -> pd.DataFrame:
    """Every clutch shot with a recorded location (a handful have none)."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute("""
            SELECT player_id, player_name, season, group_tier, loc_x, loc_y, shot_made_flag
            FROM shots_with_opponent
            WHERE loc_x IS NOT NULL AND loc_y IS NOT NULL
            """).df()


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


with shots_tab:
    shots_df = load_shots()
    shot_seasons = sorted(shots_df["season"].unique())

    shot_filter_1, shot_filter_2, shot_filter_3 = st.columns(3)
    with shot_filter_1:
        shot_tiers = st.multiselect(
            "Tiers", TIER_ORDER, default=TIER_ORDER, key="shot_tiers"
        )
        view = st.radio(
            "View", ["Accuracy heatmap", "Makes and misses"], horizontal=True
        )
    with shot_filter_2:
        shot_first, shot_last = st.select_slider(
            "Seasons",
            options=shot_seasons,
            value=(shot_seasons[0], shot_seasons[-1]),
            key="shot_seasons",
        )
    with shot_filter_3:
        shooter_options = ["All players"] + sorted(shots_df["player_name"].unique())
        shooter = st.selectbox("Player", shooter_options, key="shooter")

    selected = shots_df[
        shots_df["group_tier"].isin(shot_tiers)
        & shots_df["season"].between(shot_first, shot_last)
    ]
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
                    colorscale="RdYlGn",
                    zmin=0.25,
                    zmax=0.65,
                    colorbar=dict(title="FG%", tickformat=".0%"),
                    hovertemplate="FG%: %{z:.1%}<br>Attempts: %{customdata}<extra></extra>",
                    xgap=1,
                    ygap=1,
                )
            )
            fig.update_layout(title="Clutch field goal % by location")
            st.plotly_chart(draw_court(fig), width="stretch")
            st.caption(
                f"Each square is 2.5 × 2.5 ft. Squares with fewer than {MIN_BIN_ATTEMPTS} attempts are "
                "hidden, for the same reason as the leaderboard's shot minimum: small samples are noise."
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
                (0, "Miss", "#e4572e", "x"),
                (1, "Make", "#2e9e5b", "circle"),
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
            st.plotly_chart(draw_court(fig), width="stretch")
