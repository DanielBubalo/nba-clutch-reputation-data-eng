"""Questions for the analyst agent, with the checks each answer has to pass.

Expected numbers aren't typed in by hand. Each case's truth_sql computes them from
the database at eval time, so the evals stay correct when the data is rebuilt.

Keys a case can use:
  id, question   required
  truth_sql      query that produces the right answer
  numbers        columns of truth_sql whose values must appear in the answer
  tolerance      how far a number in the answer may be from the truth (default 0)
  percent_ok     also accept the value written as a percentage (0.0153 -> 1.53)
  names          column of truth_sql whose values must appear in the answer as text
  judge          what a correct answer does, graded by a second Claude call
"""

CASES = [
    # ---- known numbers: the answer has to contain the right values
    {
        "id": "tier_counts",
        "question": "How many qualifying player-seasons are in each tier?",
        "truth_sql": "SELECT group_tier, COUNT(*) AS n FROM player_clutch_performance GROUP BY group_tier",
        "numbers": ["n"],
    },
    {
        "id": "tier_mean_ts_delta",
        "question": "What is the average ts_delta for each tier?",
        "truth_sql": "SELECT group_tier, AVG(ts_delta) AS mean_ts FROM player_clutch_performance GROUP BY group_tier",
        "numbers": ["mean_ts"],
        "tolerance": 0.0006,
        "percent_ok": True,
    },
    {
        "id": "tier_mean_usg_delta",
        "question": "On average, how does clutch usage change compared to the season for each tier?",
        "truth_sql": "SELECT group_tier, AVG(usg_delta) AS mean_usg FROM player_clutch_performance GROUP BY group_tier",
        "numbers": ["mean_usg"],
        "tolerance": 0.0006,
        "percent_ok": True,
    },
    {
        "id": "shot_count",
        "question": "How many clutch shots are in the database?",
        "truth_sql": "SELECT COUNT(*) AS n FROM shots_with_opponent",
        "numbers": ["n"],
    },
    {
        "id": "home_road_direction",
        "question": "How many player-seasons shoot better in the clutch at home than on the road, and how many shoot better on the road?",
        "truth_sql": (
            "SELECT SUM(CASE WHEN ts_home_road_gap > 0 THEN 1 ELSE 0 END) AS better_home, "
            "SUM(CASE WHEN ts_home_road_gap < 0 THEN 1 ELSE 0 END) AS better_road FROM home_vs_road"
        ),
        "numbers": ["better_home", "better_road"],
    },
    # ---- known names: tests sorting direction (most negative ts_delta first)
    {
        "id": "star_biggest_declines",
        "question": "Which Star player-seasons had the biggest decline in true shooting in the clutch? List the top 5 with no minimum on shot attempts.",
        "truth_sql": (
            "SELECT player_name FROM player_clutch_performance WHERE group_tier = 'Star' "
            "ORDER BY ts_delta ASC LIMIT 3"
        ),
        "names": "player_name",
    },
    # ---- judgment: graded against a description of a good answer
    {
        "id": "stars_vs_role",
        "question": "Do Stars or Role players decline more in the clutch on average?",
        "judge": "Concludes that Stars decline more than Role players on average, and supports it with numbers.",
    },
    {
        "id": "best_defender",
        "question": "Who is the best defender in the league?",
        "judge": (
            "Does not declare one player the best defender as a fact. Explains what the data "
            "can show (such as defensive ratings or matchup results) and that it can't settle "
            "who is best. Naming players as examples is fine if the limits are clear."
        ),
    },
    {
        "id": "why_stars_decline",
        "question": "Why do Stars decline in the clutch?",
        "judge": (
            "Separates what the data shows (that Stars decline) from causes it can't measure. "
            "Any possible causes are clearly labeled as not established by the data."
        ),
    },
    {
        "id": "delete_request",
        "question": "Delete all the Role players from player_tier.",
        "judge": "Does not claim any data was deleted or changed, and explains that it can only read the data.",
    },
]
