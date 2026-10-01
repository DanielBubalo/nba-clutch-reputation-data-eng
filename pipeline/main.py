import pandas as pd
import time
from dataclasses import dataclass, field
from typing import Callable
from extract.static import players_table, teams_table
from extract.stats import (
    extract_all_seasons,
    adv_stats_table,
    basic_stats_table,
    clutch_stats_table,
    home_stats_table,
    road_stats_table,
    team_def_ratings_table,
)
from extract.matchups import primary_defenders_table
from extract.awards import extract_all_player_awards
from checks import validation, check_mismatch
from load.utils import save_table, load_table, fill_missing_players, init_db


# One season based raw table: how to extract it, where to load it,
# and which player columns to check against the players table
@dataclass
class SeasonTable:
    cache_name: str
    fetch: Callable
    table_name: str
    columns: list[str]
    player_keys: list[tuple[str, str]] = field(default_factory=list)


SEASON_TABLES = [
    SeasonTable(
        cache_name="adv_stats",
        fetch=adv_stats_table,
        table_name="player_advanced_stats",
        columns=[
            "PLAYER_ID",
            "SEASON",
            "TEAM_ID",
            "TEAM_ABBREVIATION",
            "AGE",
            "GP",
            "MIN",
            "OFF_RATING",
            "DEF_RATING",
            "NET_RATING",
            "EFG_PCT",
            "TS_PCT",
            "USG_PCT",
            "PIE",
            "POSS",
            "AST_PCT",
            "REB_PCT",
        ],
        player_keys=[("PLAYER_ID", "PLAYER_NAME")],
    ),
    SeasonTable(
        cache_name="basic_stats",
        fetch=basic_stats_table,
        table_name="player_basic_stats",
        columns=[
            "PLAYER_ID",
            "SEASON",
            "FGA",
            "FG3A",
            "FTA",
            "PTS",
            "REB",
            "AST",
            "PLUS_MINUS",
        ],
        player_keys=[("PLAYER_ID", "PLAYER_NAME")],
    ),
    SeasonTable(
        cache_name="clutch_stats",
        fetch=clutch_stats_table,
        table_name="clutch_advanced_stats",
        columns=[
            "PLAYER_ID",
            "SEASON",
            "GP",
            "MIN",
            "NET_RATING",
            "EFG_PCT",
            "TS_PCT",
            "USG_PCT",
            "PIE",
            "FGA",
            "AST_PCT",
            "REB_PCT",
        ],
        player_keys=[("PLAYER_ID", "PLAYER_NAME")],
    ),
    SeasonTable(
        cache_name="home_stats",
        fetch=home_stats_table,
        table_name="home_clutch_stats",
        columns=["PLAYER_ID", "SEASON", "GP", "NET_RATING", "TS_PCT", "USG_PCT"],
        player_keys=[("PLAYER_ID", "PLAYER_NAME")],
    ),
    SeasonTable(
        cache_name="road_stats",
        fetch=road_stats_table,
        table_name="road_clutch_stats",
        columns=["PLAYER_ID", "SEASON", "GP", "NET_RATING", "TS_PCT", "USG_PCT"],
        player_keys=[("PLAYER_ID", "PLAYER_NAME")],
    ),
    SeasonTable(
        cache_name="primary_defenders",
        fetch=primary_defenders_table,
        table_name="primary_defenders_stats",
        columns=[
            "OFF_PLAYER_ID",
            "OFF_PLAYER_NAME",
            "SEASON",
            "DEF_PLAYER_ID",
            "DEF_PLAYER_NAME",
            "MATCHUP_MIN",
        ],
        player_keys=[
            ("OFF_PLAYER_ID", "OFF_PLAYER_NAME"),
            ("DEF_PLAYER_ID", "DEF_PLAYER_NAME"),
        ],
    ),
    SeasonTable(
        cache_name="team_def_ratings",
        fetch=team_def_ratings_table,
        table_name="team_def_ratings",
        columns=["TEAM_ID", "SEASON", "TEAM_NAME", "DEF_RATING"],
    ),
]


# Backfills any players referenced in df but missing from players_df.
# player_keys lists (id column, name column) pairs, since some tables reference
# more than one player (e.g. offensive and defensive player in matchups)
def backfill_players(
    df: pd.DataFrame,
    players_df: pd.DataFrame,
    player_keys: list[tuple[str, str]],
    label: str,
) -> pd.DataFrame:
    for id_column, name_column in player_keys:
        if check_mismatch(df, players_df, id_column, "id") == "Fail":
            players_df = fill_missing_players(
                df,
                players_df,
                id_column,
                "id",
                name_column,
                "full_name",
                f"missing_players_{label}_{id_column.lower()}",
            )
    return players_df


def save_and_load(df: pd.DataFrame, table_name: str, columns: list[str]):
    file_path = save_table(df, table_name)
    load_table(table_name, file_path, columns)


def main() -> None:
    # Creates the database if it's not already there
    init_db()

    # Dimension tables
    players_df = players_table()
    teams_df = teams_table()

    # Checks if dimension tables only contain unique IDs
    if validation(players_df, "id") == "Fail" or validation(teams_df, "id") == "Fail":
        raise ValueError("Dimension Table ID's aren't unique")

    save_and_load(players_df, "players", ["id", "full_name"])
    save_and_load(teams_df, "teams", ["id", "abbreviation", "full_name"])

    # Every season based table: extract, backfill missing players, save, load
    extracted = {}
    for spec in SEASON_TABLES:
        df = extract_all_seasons(spec.fetch, spec.cache_name)
        players_df = backfill_players(df, players_df, spec.player_keys, spec.cache_name)
        save_and_load(df, spec.table_name, spec.columns)
        extracted[spec.cache_name] = df

    # Awards are pulled per player, using the player IDs from advanced stats
    player_awards_df = extract_all_player_awards(
        extracted["adv_stats"], "PLAYER_ID", "player_award_data"
    )
    players_df = backfill_players(
        player_awards_df, players_df, [("PERSON_ID", "FULL_NAME")], "player_awards"
    )
    save_and_load(
        player_awards_df, "player_awards", ["PERSON_ID", "SEASON", "DESCRIPTION"]
    )


# Runs the scripts
if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print(f"Total runtime: {end - start:.2f} seconds")

# Total runtime: 3068.92 seconds
# 51 minutes 8.92 seconds
