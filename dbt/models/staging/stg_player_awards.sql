SELECT
    PERSON_ID AS player_id,
    SEASON AS season,
    DESCRIPTION AS award
FROM
    {{source ('raw', 'player_awards')}}