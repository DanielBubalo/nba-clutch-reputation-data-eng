import pandas as pd
import duckdb
import time
import requests
import json
from paths import cached_data_dir, db_path
from extract.api import RETRYABLE_ERRORS, fetch_with_retry, raise_if_failures
from nba_api.stats.endpoints import ShotChartDetail


def get_player_seasons() -> pd.DataFrame:
    with duckdb.connect(str(db_path)) as con:
        result = con.sql(
            "SELECT DISTINCT player_id, season FROM player_clutch_performance"
        )
        result_df = result.df()
        return result_df


def clutch_shots_table(player_id: int, season: str) -> pd.DataFrame:
    shot_chart = ShotChartDetail(
        player_id=player_id,
        team_id=0,
        season_nullable=season,
        context_measure_simple="FGA",
        season_type_all_star="Regular Season",
        clutch_time_nullable="Last 5 Minutes",
        ahead_behind_nullable="Ahead or Behind",
        point_diff_nullable=5,
    )
    shot_chart_df = shot_chart.get_data_frames()[0]
    shot_chart_df["SEASON"] = season
    return shot_chart_df


def extract_all_shots(file_name: str) -> pd.DataFrame:
    pairs_df = get_player_seasons()
    all_shot_data = []
    path_dir = cached_data_dir / "shots"
    path_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for index, row in pairs_df.iterrows():
        player_id = row["player_id"]
        season = row["season"]
        file_path = path_dir / f"{file_name}_{player_id}_{season}.parquet"
        if (file_path).exists():
            print(f"{player_id} {season} file already there")
            df = pd.read_parquet(file_path)
        else:
            try:
                print(f"Pulling {player_id} {season} now")
                df = fetch_with_retry(clutch_shots_table, player_id, season)
                df.to_parquet(file_path, index=False)
                time.sleep(0.5)
            except RETRYABLE_ERRORS as error:
                print(f"Error pulling {player_id} {season}: {type(error).__name__}")
                failures.append(
                    {
                        "player_id": int(player_id),
                        "season": season,
                        "error": type(error).__name__,
                    }
                )
                continue
        all_shot_data.append(df)
    raise_if_failures(failures, file_name)
    result = pd.concat(all_shot_data)
    return result
