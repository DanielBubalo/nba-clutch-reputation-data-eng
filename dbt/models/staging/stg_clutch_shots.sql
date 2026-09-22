SELECT
    shot_id,
    GAME_ID AS game_id,
    PLAYER_ID AS player_id,
    PLAYER_NAME AS player_name,
    SEASON AS season,
    PERIOD AS period,
    MINUTES_REMAINING AS minutes_remaining,
    LOC_X AS loc_x,
    LOC_Y AS loc_y,
    SHOT_MADE_FLAG AS shot_made_flag,
    TEAM_ID AS team_id,
    HTM AS home_team_abv,
    VTM AS visitor_team_abv
FROM
    {{source ('raw', 'clutch_shots')}}