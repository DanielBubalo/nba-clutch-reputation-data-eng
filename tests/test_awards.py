"""Which players' awards get refetched, with the API replaced by a fake that records who was asked for."""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from extract import awards  # type: ignore # noqa: E402
from seasons import current_season, season_label, current_season_start  # type: ignore # noqa: E402


def test_only_active_players_with_old_files_and_new_players_are_fetched(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(awards, "cached_data_dir", tmp_path)
    monkeypatch.setattr(awards.time, "sleep", lambda seconds: None)
    asked_for = []

    def fake_fetch(fetch, player_id):
        asked_for.append(player_id)
        return pd.DataFrame({"PERSON_ID": [player_id], "DESCRIPTION": ["fetched"]})

    monkeypatch.setattr(awards, "fetch_with_retry", fake_fetch)

    this_season = current_season()
    long_ago = season_label(current_season_start() - 10)
    players = pd.DataFrame(
        {
            "PLAYER_ID": [1, 2, 3, 4],
            "SEASON": [long_ago, this_season, this_season, this_season],
        }
    )
    folder = tmp_path / "awards"
    folder.mkdir()
    old = datetime(
        current_season_start() - 1, 9, 1
    ).timestamp()  # before this season began
    for player_id, written in [(1, old), (2, old), (3, datetime.now().timestamp())]:
        path = folder / f"awards_{player_id}.parquet"
        pd.DataFrame({"PERSON_ID": [player_id], "DESCRIPTION": ["cached"]}).to_parquet(
            path
        )
        os.utime(path, (written, written))

    result = awards.extract_all_player_awards(players, "PLAYER_ID", "awards")

    # 1: retired, old file kept. 2: active, old file refetched. 3: active, current file kept.
    # 4: new player, fetched.
    assert sorted(asked_for) == [2, 4]
    assert len(result) == 4
