"""The season list is worked out from the date, so these tests pin the rule at its edges."""

import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from seasons import (  # type: ignore # noqa: E402
    all_seasons,
    cached_file_is_final,
    current_season,
    season_label,
    season_over,
)


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


def _file_written_on(path, day):
    path.write_text("x")
    stamp = datetime(day.year, day.month, day.day, 12).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_season_is_over_on_july_first():
    assert season_over("2025-26") == date(2026, 7, 1)


def test_missing_file_is_not_final(tmp_path):
    assert not cached_file_is_final(tmp_path / "missing.parquet", "2025-26")


def test_file_written_after_the_season_is_final(tmp_path):
    path = _file_written_on(tmp_path / "a.parquet", date(2026, 9, 16))
    assert cached_file_is_final(path, "2025-26")


def test_file_written_during_the_season_is_fetched_again(tmp_path):
    path = _file_written_on(tmp_path / "b.parquet", date(2026, 2, 1))
    assert not cached_file_is_final(path, "2025-26")


def test_current_season_is_never_final(tmp_path):
    path = _file_written_on(tmp_path / "c.parquet", date(2026, 10, 27))
    assert not cached_file_is_final(path, "2026-27")
