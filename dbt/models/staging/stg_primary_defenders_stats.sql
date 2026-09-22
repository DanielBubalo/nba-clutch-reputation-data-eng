SELECT
    OFF_PLAYER_ID AS player_id,
    OFF_PLAYER_NAME AS player_name,
    SEASON AS season,
    DEF_PLAYER_ID AS defensive_player_id,
    DEF_PLAYER_NAME AS defensive_player_name,
    MATCHUP_MIN AS matchup_minutes
FROM
    {{source ('raw', 'primary_defenders_stats')}}