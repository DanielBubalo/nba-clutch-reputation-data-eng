"""Which NBA seasons exist, worked out from today's date instead of a hard-coded list.

A new season starts each October, so from October on, the season that starts this year counts as
current. Before it tips off (October 1 to opening night) the API simply returns no rows for it.
"""

from datetime import date
from pathlib import Path

FIRST_SEASON_START = 2004  # 2004-05, the first season in the project
NEW_SEASON_MONTH = 10  # October
SEASON_OVER_MONTH = 7  # July: the regular season ends in April and the playoffs by June


def season_label(start_year: int) -> str:
    """2025 -> '2025-26', the format nba_api and every table use."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def current_season_start(today: date | None = None) -> int:
    """The year the current season started: October 2026 to September 2027 -> 2026."""
    today = today or date.today()
    return today.year if today.month >= NEW_SEASON_MONTH else today.year - 1


def current_season(today: date | None = None) -> str:
    """The season in progress, or about to start: '2026-27' from October 2026."""
    return season_label(current_season_start(today))


def all_seasons(today: date | None = None) -> list[str]:
    """Every season from 2004-05 up to and including the current one."""
    return [
        season_label(year)
        for year in range(FIRST_SEASON_START, current_season_start(today) + 1)
    ]


def season_over(season: str) -> date:
    """The date from which a season's numbers can't change: July 1 after it starts. '2025-26' -> 2026-07-01."""
    return date(int(season[:4]) + 1, SEASON_OVER_MONTH, 1)


def cached_file_is_final(path: Path, season: str) -> bool:
    """True if this cached file can be reused: its season was already over when it was written.

    The season in progress, and a season cached before it ended, get fetched again. The file's own
    timestamp records when it was written, so copy caches with timestamps kept (cp -p).
    """
    if not path.exists():
        return False
    written = date.fromtimestamp(path.stat().st_mtime)
    return written >= season_over(season)
