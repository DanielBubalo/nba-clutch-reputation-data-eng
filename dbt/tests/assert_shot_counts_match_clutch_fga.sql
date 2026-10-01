{{config (tags = ['shots'])}}
WITH
    shot_counts AS (
        SELECT
            player_id,
            season,
            COUNT(*) AS shot_rows
        FROM
            {{ref ('stg_clutch_shots')}}
        GROUP BY
            player_id,
            season
    )
SELECT
    pcp.player_id,
    pcp.season,
    pcp.fga_clutch AS official_clutch_fga,
    COALESCE(sc.shot_rows, 0) AS shot_rows
FROM
    {{ref ('player_clutch_performance')}} AS pcp
    LEFT JOIN shot_counts AS sc ON pcp.player_id = sc.player_id
    AND pcp.season = sc.season
WHERE
    pcp.fga_clutch != COALESCE(sc.shot_rows, 0)