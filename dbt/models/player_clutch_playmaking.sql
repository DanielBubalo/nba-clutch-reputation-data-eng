WITH
    base AS (
        SELECT
            *
        FROM
            {{(ref ('player_clutch_performance'))}}
    ),
    with_playmaking AS (
        SELECT
            base.*,
            adv.assist_pct AS assist_pct_season,
            adv.rebound_pct AS rebound_pct_season,
        FROM
            base
            JOIN {{source ('raw', 'player_advanced_stats')}} AS adv ON base.player_id = adv.player_id
            AND base.season = adv.season
    )
SELECT
    *
FROM
    with_playmaking