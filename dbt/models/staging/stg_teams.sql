SELECT
    id AS team_id,
    abbreviation AS team_abv,
    full_name AS team_name
FROM
    {{source ('raw', 'teams')}}