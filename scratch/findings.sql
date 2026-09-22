SELECT
    group_tier,
    COUNT(*),
    AVG(ts_delta),
    MEDIAN(ts_delta),
    STDDEV(ts_delta),
    AVG(usg_delta),
FROM
    player_clutch_performance
GROUP BY
    group_tier;