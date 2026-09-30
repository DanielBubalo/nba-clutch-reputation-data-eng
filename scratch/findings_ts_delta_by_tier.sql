SELECT
    group_tier,
    COUNT(*) AS player_seasons,
    ROUND(AVG(ts_delta), 4) AS mean_ts_delta,
    ROUND(MEDIAN(ts_delta), 4) AS median_ts_delta,
    ROUND(STDDEV(ts_delta), 3) AS stddev_ts_delta,
    ROUND(AVG(usg_delta), 4) AS mean_usg_delta
FROM
    player_clutch_performance
GROUP BY
    group_tier
ORDER BY
    CASE group_tier
        WHEN 'Role' THEN 1
        WHEN 'Star' THEN 2
        WHEN 'Olympic Gold Medalist' THEN 3
    END;