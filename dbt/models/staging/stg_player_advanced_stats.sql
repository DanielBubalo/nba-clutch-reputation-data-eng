SELECT
    PLAYER_ID AS player_id,
    SEASON AS season,
    TEAM_ID AS team_id,
    TEAM_ABBREVIATION AS team_abv,
    AGE AS age,
    GP AS games_played,
    MIN AS minutes,
    OFF_RATING AS offensive_rating,
    DEF_RATING AS defensive_rating,
    NET_RATING AS net_rating,
    EFG_PCT AS effective_field_goal_pct,
    TS_PCT AS true_shooting_pct,
    USG_PCT AS usage_pct,
    PIE AS player_impact_estimate,
    POSS AS possessions,
    AST_PCT AS assist_pct,
    REB_PCT AS rebound_pct
FROM
    {{source ('raw', 'player_advanced_stats')}}