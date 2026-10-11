"""NBA Clutch Reputation dashboard.

Run from the project root:
    streamlit run dashboard/app.py
"""

import math
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

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
            SELECT player_name, season, group_tier, team_abv,
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

overview_tab, leaderboard_tab = st.tabs(["Overview", "Leaderboards"])


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
