WITH
    star_from AS (
        SELECT
            player_id,
            MIN(CAST(LEFT(season, 4) AS INT)) + 1 AS star_from_year
        FROM
            {{ref ('stg_player_awards')}}
        WHERE
            award IN (
                'All-NBA',
                'NBA Most Valuable Player',
                'NBA Finals Most Valuable Player',
                'NBA All-Star Most Valuable Player',
                'NBA All-Star'
            )
        GROUP BY
            player_id
    ),
    gold_from AS (
        SELECT
            player_id,
            MIN(CAST(season AS INT)) AS gold_from_year
        FROM
            {{ref ('stg_player_awards')}}
        WHERE
            award = 'Olympic Gold Medal'
        GROUP BY
            player_id
    ),
    player_seasons AS (
        SELECT DISTINCT
            player_id,
            season,
            CAST(LEFT(season, 4) AS INT) AS season_year
        FROM
            {{ref ('stg_player_advanced_stats')}}
    )
SELECT
    ps.player_id,
    ps.season,
    CASE
        WHEN sf.star_from_year <= ps.season_year
        AND gf.gold_from_year <= ps.season_year THEN 'Olympic Gold Medalist'
        WHEN sf.star_from_year <= ps.season_year THEN 'Star'
        ELSE 'Role'
    END AS group_tier
FROM
    player_seasons AS ps
    LEFT JOIN star_from AS sf ON ps.player_id = sf.player_id
    LEFT JOIN gold_from AS gf ON ps.player_id = gf.player_id