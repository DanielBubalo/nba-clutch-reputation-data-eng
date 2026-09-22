WITH
    star_players AS (
        SELECT
            *
        FROM
            {{ref ('player_clutch_performance')}}
        WHERE
            group_tier IN ('Star', 'Olympic Gold Medalist')
    ),
    award_seasons AS (
        SELECT
            player_id,
            MIN(season) AS first_award_season
        FROM
            {{ref ('stg_player_awards')}}
        WHERE
            LENGTH(season) = 7
        GROUP BY
            player_id
    ),
    with_first_award AS (
        SELECT
            star.*,
            awards.first_award_season
        FROM
            star_players AS star
            JOIN award_seasons AS awards ON star.player_id = awards.player_id
    )
SELECT
    *
FROM
    with_first_award