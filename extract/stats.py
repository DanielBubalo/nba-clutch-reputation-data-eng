import pandas as pd
import time
from pathlib import Path
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashplayerclutch


# Collects the data from the tables below and loops through every season
def extract_all_seasons(table, file_name: str) -> pd.DataFrame:
    seasons = [f"{str(season)}-{str(season + 1)[-2:]}" for season in range(2004, 2026)]
    all_season_data = []
    path_dir = Path(f"cached_data/seasons")
    path_dir.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        file_path = Path(f"cached_data/seasons/{file_name}_{season}.parquet")
        if (file_path).exists():
            print(f"{season} file already there")
            df = pd.read_parquet(file_path)
        else:
            print(f"Pulling {season} now")
            df = table(season)
            df.to_parquet(file_path, index=False)
            time.sleep(0.5)
        all_season_data.append(df)
    result = pd.concat(all_season_data)
    return result


# Extracts data from the leaguedashplayerstats endpoint (advanced season stats), per given season
def adv_stats_table(season: str) -> pd.DataFrame:
    adv_stats = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        measure_type_detailed_defense="Advanced",
        season_type_all_star="Regular Season",
    )
    adv_stats_df = adv_stats.get_data_frames()[0]
    adv_stats_df["SEASON"] = season
    return adv_stats_df


# Extracts data from the leaguedashplayerclutch endpoint (advanced clutch stats), per given season
def clutch_stats_table(season: str) -> pd.DataFrame:
    clutch_stats = leaguedashplayerclutch.LeagueDashPlayerClutch(
        season=season,
        measure_type_detailed_defense="Advanced",
        season_type_all_star="Regular Season",
    )
    clutch_stats_df = clutch_stats.get_data_frames()[0]
    clutch_stats_df["SEASON"] = season
    return clutch_stats_df


# Extracts data from the leaguedashplayerclutch endpoint (home clutch stats), per given season
def home_stats_table(season: str) -> pd.DataFrame:
    home_stats = leaguedashplayerclutch.LeagueDashPlayerClutch(
        season=season,
        measure_type_detailed_defense="Advanced",
        season_type_all_star="Regular Season",
        location_nullable="Home",
    )
    home_stats_df = home_stats.get_data_frames()[0]
    home_stats_df["SEASON"] = season
    return home_stats_df


# Extracts data from the leaguedashplayerclutch endpoint (road clutch stats), per given season
def road_stats_table(season: str) -> pd.DataFrame:
    road_stats = leaguedashplayerclutch.LeagueDashPlayerClutch(
        season=season,
        measure_type_detailed_defense="Advanced",
        season_type_all_star="Regular Season",
        location_nullable="Road",
    )
    road_stats_df = road_stats.get_data_frames()[0]
    road_stats_df["SEASON"] = season
    return road_stats_df
