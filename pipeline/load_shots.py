from extract.shots import extract_all_shots
from checks import check_mismatch
from load.utils import save_table, load_table, fill_missing_players
from extract.static import players_table
import time


def main() -> None:
    players_df = players_table()

    clutch_shots_df = extract_all_shots("clutch_shots")

    if check_mismatch(clutch_shots_df, players_df, "PLAYER_ID", "id") == "Fail":
        players_df = fill_missing_players(
            clutch_shots_df,
            players_df,
            "PLAYER_ID",
            "id",
            "PLAYER_NAME",
            "full_name",
            "missing_players_clutch_shots",
        )

    file_path_clutch_shots = save_table(clutch_shots_df, "clutch_shots")
    clutch_shots_columns = {
        "PLAYER_ID": "player_id",
        "SEASON": "season",
        "GAME_ID": "game_id",
        "PLAYER_NAME": "player_name",
        "PERIOD": "period",
        "MINUTES_REMAINING": "minutes_remaining",
        "LOC_X": "loc_x",
        "LOC_Y": "loc_y",
        "SHOT_MADE_FLAG": "shot_made_flag",
        "TEAM_ID": "team_id",
        "HTM": "home_team_abv",
        "VTM": "visitor_team_abv",
    }
    load_table("clutch_shots", file_path_clutch_shots, clutch_shots_columns)


if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print(f"Total runtime: {end - start:.2f} seconds")

# Runtime: 6541.67 seconds
# 1 hour, 49 minutes, 1.67 seconds
