SELECT DISTINCT
    team_abv,
    team_id
FROM
    {{ref ('stg_player_advanced_stats')}}
UNION
SELECT
    team_abv,
    team_id
FROM
    {{ref ('stg_teams')}}