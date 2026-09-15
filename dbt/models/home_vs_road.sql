WITH
    home_road_stats AS (
        SELECT
            home_clutch.player_id,
            home_clutch.season,
            home_clutch.games_played AS games_played_home,
            road_clutch.games_played AS games_played_road,
            home_clutch.true_shooting_pct AS true_shooting_pct_home,
            road_clutch.true_shooting_pct AS true_shooting_pct_road,
            home_clutch.net_rating AS net_rating_home,
            road_clutch.net_rating AS net_rating_road,
            home_clutch.usage_pct AS usage_pct_home,
            road_clutch.usage_pct AS usage_pct_road,
            home_clutch.true_shooting_pct - road_clutch.true_shooting_pct AS ts_home_road_gap
        FROM
            {{source ('raw', 'home_clutch_stats')}} AS home_clutch
            JOIN {{source ('raw', 'road_clutch_stats')}} AS road_clutch ON home_clutch.player_id = road_clutch.player_id
            AND home_clutch.season = road_clutch.season
        WHERE
            home_clutch.games_played >= 8
            AND road_clutch.games_played >= 8
    ),
    with_names AS (
        SELECT
            home_road.*,
            performance.player_name,
            performance.group_tier
        FROM
            home_road_stats AS home_road
            JOIN {{ref ('player_clutch_performance')}} AS performance ON home_road.player_id = performance.player_id
            AND home_road.season = performance.season
    )
SELECT
    *
FROM
    with_names