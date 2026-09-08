import pandas as pd
from nba_api.stats.static import players, teams


# Extracts static player data
def players_table() -> pd.DataFrame:
    all_players = players.get_players()
    players_df = pd.DataFrame(all_players)
    return players_df


# Extracts static team data
def teams_table() -> pd.DataFrame:
    all_teams = teams.get_teams()
    teams_df = pd.DataFrame(all_teams)
    return teams_df
