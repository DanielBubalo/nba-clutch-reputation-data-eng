SELECT
    PLAYER_ID AS player_id,
    SEASON AS season,
    GP AS games_played,
    MIN AS minutes,
    NET_RATING AS net_rating,
    EFG_PCT AS effective_field_goal_pct,
    TS_PCT AS true_shooting_pct,
    USG_PCT AS usage_pct,
    PIE AS player_impact_estimate,
    FGA AS field_goals_attempted,
    AST_PCT AS assist_pct,
    REB_PCT AS rebound_pct
FROM
    {{source ('raw', 'clutch_advanced_stats')}}