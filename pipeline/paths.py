import os
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent

project_root = pipeline_root.parent

# Which database and cache this run uses. With nothing set, they're the original ones, so nothing
# changes. Set NBA_DB_PATH and NBA_CACHE_DIR (absolute paths) to work in a separate environment,
# for example a live copy that fetches the current season without touching the demo database.
db_path = Path(
    os.environ.get("NBA_DB_PATH", project_root / "nba_clutch.duckdb")
).resolve()

cached_data_dir = Path(
    os.environ.get("NBA_CACHE_DIR", pipeline_root / "cached_data")
).resolve()
