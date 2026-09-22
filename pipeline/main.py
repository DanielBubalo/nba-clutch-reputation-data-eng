import time
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
from load.utils import save_table, load_table, fill_missing_players


def main() -> None:
    # Variables to hold dimension tables
    players_df = players_table()
    teams_df = teams_table()

    # Checks if dimension tables only contain unique IDs
    if validation(players_df, "id") == "Fail" or validation(teams_df, "id") == "Fail":
        raise ValueError("Dimension Table ID's aren't unique")

    # Saves and loads the data into the player table
    file_path_players = save_table(players_df, "players")
    player_columns = ["id", "full_name"]
    load_table("players", file_path_players, player_columns)

    # Saves and loads the data into the teams table
    file_path_teams = save_table(teams_df, "teams")
    team_columns = [
        "id",
        "abbreviation",
        "full_name",
    ]
    load_table("teams", file_path_teams, team_columns)

    # Stores the extracted data from every season (adv_stats_table)
    adv_stats_df = extract_all_seasons(adv_stats_table, "adv_stats")

    # Checks to see if data is missing between the advance stats and player table and fills it in
    if check_mismatch(adv_stats_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            adv_stats_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_adv",
        )

    # Saves and loads the data into the player_advanced_stats staging table, renames the column names to fit staging names
    file_path_adv = save_table(adv_stats_df, "player_advanced_stats")
    adv_stats_columns = [
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
    ]
    load_table("player_advanced_stats", file_path_adv, adv_stats_columns)

    basic_stats_df = extract_all_seasons(basic_stats_table, "basic_stats")

    if check_mismatch(basic_stats_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            basic_stats_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_basic",
        )

    file_path_basic = save_table(basic_stats_df, "player_basic_stats")
    basic_stats_columns = [
        "PLAYER_ID",
        "SEASON",
        "FGA",
        "FG3A",
        "FTA",
        "PTS",
        "REB",
        "AST",
        "PLUS_MINUS",
    ]
    load_table("player_basic_stats", file_path_basic, basic_stats_columns)

    # Stores the extracted data from every season (clutch_stats)
    clutch_stats_df = extract_all_seasons(clutch_stats_table, "clutch_stats")

    # Checks to see if data is missing between the clutch stats and player table and fills it in
    if check_mismatch(clutch_stats_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            clutch_stats_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_clutch",
        )

    # Saves and loads the data into the clutch_advanced_stats staging table, renames the column names to fit staging names
    file_path_clutch = save_table(clutch_stats_df, "clutch_advanced_stats")
    clutch_stats_columns = [
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
    ]
    load_table("clutch_advanced_stats", file_path_clutch, clutch_stats_columns)

    # Stores the extracted data from every season (home_stats_table)
    home_stats_df = extract_all_seasons(home_stats_table, "home_stats")

    # Checks to see if data is missing between the home stats and player table and fills it in
    if check_mismatch(home_stats_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            home_stats_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_home",
        )

    # Saves and loads the data into the home_clutch_stats staging table, renames the column names to fit staging names
    file_path_home = save_table(home_stats_df, "home_clutch_stats")
    home_stats_columns = [
        "PLAYER_ID",
        "SEASON",
        "GP",
        "NET_RATING",
        "TS_PCT",
        "USG_PCT",
    ]
    load_table("home_clutch_stats", file_path_home, home_stats_columns)

    # Stores the extracted data from every season (road_stats_df)
    road_stats_df = extract_all_seasons(road_stats_table, "road_stats")

    # Checks to see if data is missing between the road stats and player table and fills it in
    if check_mismatch(road_stats_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            road_stats_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_road",
        )

    # Saves and loads the data into the road_clutch_stats staging table, renames the column names to fit staging names
    file_path_road = save_table(road_stats_df, "road_clutch_stats")
    road_stats_columns = [
        "PLAYER_ID",
        "SEASON",
        "GP",
        "NET_RATING",
        "TS_PCT",
        "USG_PCT",
    ]
    load_table("road_clutch_stats", file_path_road, road_stats_columns)

    # Stores the extracted data from every season (primary_defenders_df)
    primary_defenders_df = extract_all_seasons(
        primary_defenders_table, "primary_defenders"
    )

    # Checks to see if data is missing between the primary defenders and player table and fills it in (offensive player IDs)
    if (
        check_mismatch(primary_defenders_df, players_df, "OFF_PLAYER_ID", "id")
        == "Fail"
    ):
        players_df = fill_missing_players(
            primary_defenders_df,
            players_df,
            "OFF_PLAYER_ID",
            "id",
            "OFF_PLAYER_NAME",
            "full_name",
            "missing_primary_defenders_off",
        )
    # Checks to see if data is missing between the primary defenders and player table and fills it in (defensive player IDs)
    if (
        check_mismatch(primary_defenders_df, players_df, "DEF_PLAYER_ID", "id")
        == "Fail"
    ):
        players_df = fill_missing_players(
            primary_defenders_df,
            players_df,
            "DEF_PLAYER_ID",
            "id",
            "DEF_PLAYER_NAME",
            "full_name",
            "missing_primary_defenders_def",
        )

    # Saves and loads the data into the primary_defenders_stats staging table, renames the column names to fit staging names
    file_path_defenders = save_table(primary_defenders_df, "primary_defenders_stats")
    primary_defenders_columns = [
        "OFF_PLAYER_ID",
        "OFF_PLAYER_NAME",
        "SEASON",
        "DEF_PLAYER_ID",
        "DEF_PLAYER_NAME",
        "MATCHUP_MIN",
    ]
    load_table(
        "primary_defenders_stats", file_path_defenders, primary_defenders_columns
    )

    # Stores the extracted data from every season (player_awards_df)
    player_awards_df = extract_all_player_awards(
        adv_stats_df, "PLAYER_ID", "player_award_data"
    )

    # Checks to see if data is missing between the player awards and player table and fills it in
    if check_mismatch(player_awards_df, players_df, "PERSON_ID", "id") == "Fail":
        players_df = fill_missing_players(
            player_awards_df,
            players_df,
            "PERSON_ID",
            "id",
            "FULL_NAME",
            "full_name",
            "missing_player_awards",
        )

    # Saves and loads the data into the player_awards staging table, renames the column names to fit staging names
    file_path_awards = save_table(player_awards_df, "player_awards")
    player_awards_columns = [
        "PERSON_ID",
        "SEASON",
        "DESCRIPTION",
    ]
    load_table("player_awards", file_path_awards, player_awards_columns)

    team_def_ratings_df = extract_all_seasons(
        team_def_ratings_table, "team_def_ratings"
    )

    file_path_team_def = save_table(team_def_ratings_df, "team_def_ratings")
    team_def_ratings_columns = [
        "TEAM_ID",
        "SEASON",
        "TEAM_NAME",
        "DEF_RATING",
    ]
    load_table("team_def_ratings", file_path_team_def, team_def_ratings_columns)


# Runs the scripts
if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print(f"Total runtime: {end - start:.2f} seconds")

# Total runtime: 3068.92 seconds
# 51 minutes 8.92 seconds
