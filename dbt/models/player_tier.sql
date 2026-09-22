WITH
    star_players AS (
        SELECT DISTINCT
            player_id
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
    ),
    gold_medalists AS (
        SELECT DISTINCT
            player_id
        FROM
            {{ref ('stg_player_awards')}}
        WHERE
            award = 'Olympic Gold Medal'
    ),
    eligible_players AS (
        SELECT
            player_id
        FROM
            star_players
        UNION
        SELECT
            player_id
        FROM
            gold_medalists
        UNION
        SELECT
            player_id
        FROM
            {{ref ('stg_player_advanced_stats')}}
        WHERE
            possessions > 100
    )
SELECT
    player_id,
    CASE
        WHEN player_id IN (
            SELECT
                player_id
            FROM
                gold_medalists
        )
        AND player_id IN (
            SELECT
                player_id
            FROM
                star_players
        ) THEN 'Olympic Gold Medalist'
        WHEN player_id IN (
            SELECT
                player_id
            FROM
                star_players
        ) THEN 'Star'
        ELSE 'Role'
    END AS group_tier
FROM
    eligible_players