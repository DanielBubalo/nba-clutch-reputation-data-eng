"""Incremental season loads: replace_seasons, tested on a throwaway DuckDB file, never the real one."""

import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from load import utils as load_utils  # type: ignore # noqa: E402

COLUMNS = ["PLAYER_ID", "SEASON", "PTS"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh database with one small season table, used instead of the real one."""
    path = tmp_path / "test.duckdb"
    monkeypatch.setattr(load_utils, "db_path", path)
    with duckdb.connect(str(path)) as con:
        con.execute(
            "CREATE TABLE stats (PLAYER_ID INT, SEASON VARCHAR, PTS INT, NOTE VARCHAR, "
            "PRIMARY KEY (PLAYER_ID, SEASON))"
        )
    return path


def stored(db):
    with duckdb.connect(str(db)) as con:
        return con.execute(
            "SELECT PLAYER_ID, SEASON, PTS FROM stats ORDER BY SEASON, PLAYER_ID"
        ).fetchall()


def store(db, rows):
    with duckdb.connect(str(db)) as con:
        con.executemany(
            "INSERT INTO stats (PLAYER_ID, SEASON, PTS) VALUES (?, ?, ?)", rows
        )


def parquet(tmp_path, rows):
    path = tmp_path / "pulled.parquet"
    pd.DataFrame(rows, columns=COLUMNS).to_parquet(path, index=False)
    return path


def test_new_database_gets_every_season(db, tmp_path):
    file = parquet(tmp_path, [(1, "2024-25", 10), (1, "2025-26", 20)])
    assert load_utils.replace_seasons("stats", file, COLUMNS, fetched_seasons=[]) == [
        "2024-25",
        "2025-26",
    ]
    assert stored(db) == [(1, "2024-25", 10), (1, "2025-26", 20)]


def test_only_the_fetched_season_is_replaced(db, tmp_path):
    store(db, [(1, "2024-25", 10), (1, "2025-26", 20), (9, "2025-26", 5)])
    # The finished season comes back different (from the cache): it must not be rewritten.
    # The fetched season changed, and player 9 dropped out of it.
    file = parquet(tmp_path, [(1, "2024-25", 999), (1, "2025-26", 21)])
    assert load_utils.replace_seasons(
        "stats", file, COLUMNS, fetched_seasons=["2025-26"]
    ) == ["2025-26"]
    assert stored(db) == [(1, "2024-25", 10), (1, "2025-26", 21)]


def test_an_empty_response_never_wipes_a_stored_season(db, tmp_path):
    store(db, [(1, "2024-25", 10), (1, "2025-26", 20)])
    file = parquet(
        tmp_path, [(1, "2024-25", 10)]
    )  # 2025-26 was fetched but came back empty
    assert (
        load_utils.replace_seasons("stats", file, COLUMNS, fetched_seasons=["2025-26"])
        == []
    )
    assert stored(db) == [(1, "2024-25", 10), (1, "2025-26", 20)]


def test_nothing_changed_writes_nothing(db, tmp_path):
    store(db, [(1, "2024-25", 10)])
    file = parquet(tmp_path, [(1, "2024-25", 10)])
    assert load_utils.replace_seasons("stats", file, COLUMNS, fetched_seasons=[]) == []
    assert stored(db) == [(1, "2024-25", 10)]


def test_a_failed_insert_rolls_back_the_delete(db, tmp_path):
    store(db, [(1, "2025-26", 20)])
    file = parquet(tmp_path, [(1, "2025-26", 21)])
    with pytest.raises(duckdb.Error):
        # NOTE is in the table but not in the file, so the insert fails after the delete ran
        load_utils.replace_seasons(
            "stats", file, COLUMNS + ["NOTE"], fetched_seasons=["2025-26"]
        )
    assert stored(db) == [(1, "2025-26", 20)]
