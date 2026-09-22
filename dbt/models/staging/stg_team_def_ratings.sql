SELECT
    TEAM_ID AS team_id,
    SEASON AS season,
    TEAM_NAME AS team_name,
    DEF_RATING AS defensive_rating
FROM
    {{source ('raw', 'team_def_ratings')}}