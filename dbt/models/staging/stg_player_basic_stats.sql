SELECT
    PLAYER_ID AS player_id,
    SEASON AS season,
    FGA AS field_goals_attempted,
    FG3A AS three_point_field_goals_attempted,
    FTA AS free_throws_attempted,
    PTS AS points,
    REB AS rebounds,
    AST AS assists,
    PLUS_MINUS AS plus_minus
FROM
    {{source ('raw', 'player_basic_stats')}}