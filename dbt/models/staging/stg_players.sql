SELECT
    id AS player_id,
    full_name AS player_name
FROM
    {{source ('raw', 'players')}}