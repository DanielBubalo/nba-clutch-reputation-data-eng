WITH
    base AS (
        SELECT
            *
        FROM
            {{source ('raw', 'primary_defenders_stats')}}
    ),
    with_defender_rating AS (
        SELECT
            base.*,
            adv.defensive_rating AS defender_defensive_rating
        FROM
            base
            JOIN {{source ('raw', 'player_advanced_stats')}} AS adv ON base.defensive_player_id = adv.player_id
            AND base.season = adv.season
    ),
    with_ts_delta AS (
        SELECT
            wdr.*,
            performance.ts_delta,
            performance.group_tier
        FROM
            with_defender_rating AS wdr
            JOIN {{ref ('player_clutch_performance')}} AS performance ON wdr.player_id = performance.player_id
            AND wdr.season = performance.season
    )
SELECT
    *
FROM
    with_ts_delta