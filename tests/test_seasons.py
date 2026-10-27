"""The season list is worked out from the date, so these tests pin the rule at its edges."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from seasons import all_seasons, current_season, season_label  # type: ignore # noqa: E402


def test_season_label_format():
    assert season_label(2025) == "2025-26"
    assert season_label(2099) == "2099-00"


def test_new_season_counts_from_october():
    assert current_season(date(2026, 9, 30)) == "2025-26"
    assert current_season(date(2026, 10, 1)) == "2026-27"


def test_season_carries_over_the_new_year():
    assert current_season(date(2027, 1, 15)) == "2026-27"
    assert current_season(date(2027, 4, 11)) == "2026-27"


def test_all_seasons_runs_from_2004_05_to_the_current_one():
    seasons = all_seasons(date(2026, 10, 27))
    assert seasons[0] == "2004-05"
    assert seasons[-1] == "2026-27"
    assert len(seasons) == 23


def test_before_october_matches_the_old_hard_coded_list():
    old_list = [f"{year}-{str(year + 1)[-2:]}" for year in range(2004, 2026)]
    assert all_seasons(date(2026, 9, 1)) == old_list
