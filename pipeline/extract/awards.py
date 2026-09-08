import pandas as pd
import time
import requests
from pathlib import Path
from nba_api.stats.endpoints import PlayerAwards


# Collects players ideas from extracted data (only unique ID's)
def get_unique_player_ids(table: pd.DataFrame, column: str) -> set:
    player_ids = set(table[column])
    return player_ids


# Loops through every player id, extracting the awards of that player
def extract_all_player_awards(
    table: pd.DataFrame, column: str, file_name: str
) -> pd.DataFrame:
    player_ids = get_unique_player_ids(table, column)
    all_player_data = []
    path_dir = Path(f"cached_data/awards")
    path_dir.mkdir(parents=True, exist_ok=True)
    for player_id in player_ids:
        file_path = Path(f"cached_data/awards/{file_name}_{player_id}.parquet")
        if (file_path).exists():
            print(f"{player_id} file already there")
            df = pd.read_parquet(file_path)
        else:
            try:
                print(f"Pulling {player_id} now")
                df = player_awards_table(player_id)
                df.to_parquet(file_path, index=False)
                time.sleep(0.5)
            except requests.exceptions.ReadTimeout:
                print(f"Error pulling {player_id}")
                continue
        all_player_data.append(df)
    result = pd.concat(all_player_data)
    return result


# Extracts data from the PlayerAwards endpoint (player award descriptions), per given player ID
def player_awards_table(player_id: int) -> pd.DataFrame:
    player_awards = PlayerAwards(player_id=player_id)
    player_awards_df = player_awards.get_data_frames()[0]
    player_awards_df = player_awards_df[
        player_awards_df["WEEK"].isna() & player_awards_df["MONTH"].isna()
    ]
    player_awards_df["FULL_NAME"] = player_awards_df["FIRST_NAME"] + " " + player_awards_df["LAST_NAME"]
    return player_awards_df
