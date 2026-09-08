import pandas as pd
from nba_api.stats.endpoints import leagueseasonmatchups


# Extracts data from the leagueseasonmatchups endpoint (primary defender stats), per given season
def primary_defenders_table(season) -> pd.DataFrame:
    primary_defenders = leagueseasonmatchups.LeagueSeasonMatchups(
        season=season, season_type_playoffs="Regular Season"
    )
    primary_defenders_df = primary_defenders.get_data_frames()[0]
    primary_defenders_df["SEASON"] = season
    return primary_defenders_df
