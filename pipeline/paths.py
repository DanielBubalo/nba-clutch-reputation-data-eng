from pathlib import Path

pipeline_root = Path(__file__).resolve().parent

project_root = pipeline_root.parent

cached_data_dir = pipeline_root / "cached_data"

db_path = project_root / "nba_clutch.duckdb"