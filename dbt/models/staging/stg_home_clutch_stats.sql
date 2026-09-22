SELECT
    PLAYER_ID AS player_id,
    SEASON AS season,
    GP AS games_played,
    NET_RATING AS net_rating,
    TS_PCT AS true_shooting_pct,
    USG_PCT AS usage_pct
FROM
    {{source ('raw', 'home_clutch_stats')}}