WITH
    home_lookup AS (
        SELECT
            cs.shot_id,
            t.team_id AS home_team_id
        FROM
            {{ref ('stg_clutch_shots')}} cs
            JOIN {{ref ('stg_teams')}} t ON cs.home_team_abv = t.team_abv
    ),
    visitor_lookup AS (
        SELECT
            cs.shot_id,
            t.team_id AS visitor_team_id
        FROM
            {{ref ('stg_clutch_shots')}} cs
            JOIN {{ref ('stg_teams')}} t ON cs.visitor_team_abv = t.team_abv
    ),
    with_opponent AS (
        SELECT
            cs.shot_id,
            cs.player_id,
            cs.player_name,
            cs.season,
            cs.game_id,
            cs.period,
            cs.minutes_remaining,
            cs.loc_x,
            cs.loc_y,
            cs.shot_made_flag,
            CASE
                WHEN hl.home_team_id = cs.team_id THEN vl.visitor_team_id
                ELSE hl.home_team_id
            END AS opponent_team_id
        FROM
            {{ref ('stg_clutch_shots')}} cs
            JOIN home_lookup hl ON cs.shot_id = hl.shot_id
            JOIN visitor_lookup vl ON cs.shot_id = vl.shot_id
    )
SELECT
    wo.shot_id,
    wo.player_id,
    wo.player_name,
    wo.season,
    wo.game_id,
    wo.period,
    wo.minutes_remaining,
    wo.loc_x,
    wo.loc_y,
    wo.shot_made_flag,
    wo.opponent_team_id,
    tdr.defensive_rating,
    pcp.ts_delta,
    pcp.group_tier
FROM
    with_opponent wo
    JOIN {{ref ('stg_team_def_ratings')}} tdr ON wo.opponent_team_id = tdr.team_id
    AND wo.season = tdr.season
    JOIN {{ref ('player_clutch_performance')}} pcp ON wo.player_id = pcp.player_id
    AND wo.season = pcp.season