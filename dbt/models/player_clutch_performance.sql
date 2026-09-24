{{config (materialized = 'table')}}
WITH
    season_stats AS (
        SELECT
            adv.player_id,
            adv.season,
            adv.team_id,
            adv.team_abv,
            adv.age,
            adv.games_played,
            adv.minutes,
            adv.offensive_rating,
            adv.defensive_rating,
            adv.net_rating,
            adv.effective_field_goal_pct,
            adv.true_shooting_pct,
            adv.usage_pct,
            adv.player_impact_estimate,
            adv.possessions,
            basic.field_goals_attempted,
            basic.three_point_field_goals_attempted,
            basic.free_throws_attempted,
            basic.points,
            basic.rebounds,
            basic.assists,
            basic.plus_minus
        FROM
            {{ref ('stg_player_advanced_stats')}} AS adv
            JOIN {{ref ('stg_player_basic_stats')}} AS basic ON adv.player_id = basic.player_id
            AND adv.season = basic.season
        WHERE
            basic.field_goals_attempted > 100
    ),
    with_tier AS (
        SELECT
            *
        FROM
            season_stats AS season
            JOIN {{ref ('player_tier')}} AS tier ON season.player_id = tier.player_id
    ),
    with_clutch AS (
        SELECT
            season.player_id,
            season.season,
            clutch.games_played AS games_played_clutch,
            season.games_played AS games_played_season,
            clutch.minutes AS minutes_clutch,
            season.minutes AS minutes_season,
            clutch.effective_field_goal_pct AS efg_clutch,
            season.effective_field_goal_pct AS efg_season,
            clutch.true_shooting_pct AS ts_clutch,
            season.true_shooting_pct AS ts_season,
            clutch.usage_pct AS usg_clutch,
            season.usage_pct AS usg_season,
            clutch.net_rating AS net_rating_clutch,
            season.net_rating AS net_rating_season,
            clutch.player_impact_estimate AS pie_clutch,
            season.player_impact_estimate AS pie_season,
            clutch.field_goals_attempted AS fga_clutch,
            season.field_goals_attempted AS fga_season,
            clutch.assist_pct AS assist_pct_clutch,
            clutch.rebound_pct AS rebound_pct_clutch,
            season.team_id,
            season.team_abv,
            season.age,
            season.offensive_rating,
            season.defensive_rating,
            season.possessions,
            season.three_point_field_goals_attempted,
            season.free_throws_attempted,
            season.points,
            season.rebounds,
            season.assists,
            season.plus_minus,
            season.group_tier,
            clutch.true_shooting_pct - season.true_shooting_pct AS ts_delta,
            clutch.usage_pct - season.usage_pct AS usg_delta,
            players.player_name
        FROM
            with_tier AS season
            JOIN {{ref ('stg_clutch_advanced_stats')}} AS clutch ON season.player_id = clutch.player_id
            AND season.season = clutch.season
            JOIN {{ref ('stg_players')}} AS players ON season.player_id = players.player_id
        WHERE
            clutch.games_played >= 15
    )
SELECT
    *
FROM
    with_clutch