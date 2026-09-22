INSERT INTO player_advanced_stats (PLAYER_ID, SEASON, TEAM_ID, TEAM_ABBREVIATION, AGE, GP, MIN, OFF_RATING, DEF_RATING, NET_RATING, EFG_PCT, TS_PCT, USG_PCT, PIE, POSS, AST_PCT, REB_PCT)
SELECT PLAYER_ID, SEASON, TEAM_ID, TEAM_ABBREVIATION, AGE, GP, MIN, OFF_RATING, DEF_RATING, NET_RATING, EFG_PCT, TS_PCT, USG_PCT, PIE, POSS, AST_PCT, REB_PCT
FROM read_parquet('pipeline/cached_data/player_advanced_stats/player_advanced_stats.parquet');

INSERT INTO player_basic_stats (PLAYER_ID, SEASON, FGA, FG3A, FTA, PTS, REB, AST, PLUS_MINUS)
SELECT PLAYER_ID, SEASON, FGA, FG3A, FTA, PTS, REB, AST, PLUS_MINUS
FROM read_parquet('pipeline/cached_data/player_basic_stats/player_basic_stats.parquet');

INSERT INTO clutch_advanced_stats (PLAYER_ID, SEASON, GP, MIN, NET_RATING, EFG_PCT, TS_PCT, USG_PCT, PIE, FGA, AST_PCT, REB_PCT)
SELECT PLAYER_ID, SEASON, GP, MIN, NET_RATING, EFG_PCT, TS_PCT, USG_PCT, PIE, FGA, AST_PCT, REB_PCT
FROM read_parquet('pipeline/cached_data/clutch_advanced_stats/clutch_advanced_stats.parquet');

INSERT INTO home_clutch_stats (PLAYER_ID, SEASON, GP, NET_RATING, TS_PCT, USG_PCT)
SELECT PLAYER_ID, SEASON, GP, NET_RATING, TS_PCT, USG_PCT
FROM read_parquet('pipeline/cached_data/home_clutch_stats/home_clutch_stats.parquet');

INSERT INTO road_clutch_stats (PLAYER_ID, SEASON, GP, NET_RATING, TS_PCT, USG_PCT)
SELECT PLAYER_ID, SEASON, GP, NET_RATING, TS_PCT, USG_PCT
FROM read_parquet('pipeline/cached_data/road_clutch_stats/road_clutch_stats.parquet');

INSERT INTO primary_defenders_stats (OFF_PLAYER_ID, OFF_PLAYER_NAME, SEASON, DEF_PLAYER_ID, DEF_PLAYER_NAME, MATCHUP_MIN)
SELECT OFF_PLAYER_ID, OFF_PLAYER_NAME, SEASON, DEF_PLAYER_ID, DEF_PLAYER_NAME, MATCHUP_MIN
FROM read_parquet('pipeline/cached_data/primary_defenders_stats/primary_defenders_stats.parquet');
