# NBA Clutch Reputation Database

An ELT pipeline that extracts NBA player and team statistics via `nba_api`, loads them into DuckDB, and transforms them with dbt to analyze how players' clutch performance compares to their season-long performance and reputation tier — do "Stars" actually perform better in the clutch, or does reputation outpace results?

## Architecture

```
nba_api  →  Python (Extract + Load)  →  DuckDB  →  dbt (Transform)  →  7 analysis models
                                                                              ↓
                                                              Orchestrated end-to-end by Airflow (Docker)
```

The pipeline follows a strict ELT pattern with three sequential stages:

1. **Extract + Load** (`pipeline/main.py`) — pulls raw data from 8 `nba_api` endpoints across every season from 2004-05 to 2025-26, caches responses as parquet, and loads them into DuckDB as raw tables.
2. **Transform** (`dbt build`) — builds 7 analysis models and runs 12 data tests on top of the raw tables entirely in SQL.
3. **Shot extraction** (`pipeline/load_shots.py`) — pulls clutch shot-chart data, scoped to the ~5,086 player-seasons already qualifying in the `player_clutch_performance` dbt model (rather than every player-season in NBA history). Because this step queries a dbt model, it must run *after* stage 2, not alongside stage 1 — this is why it's a separate script rather than folded into `main.py`.

All three stages are orchestrated as a single Airflow DAG (`airflow/dags/nba_pipeline.py`), running in a local Docker Compose environment (CeleryExecutor, Postgres, Redis).

## Data Sources

All data comes from the unofficial `nba_api` Python package, covering Regular Season data from the 2004-05 season through 2025-26:

| Endpoint | Data |
|---|---|
| `LeagueDashPlayerStats` (Advanced) | Season-long advanced stats (ratings, efficiency, usage) |
| `LeagueDashPlayerStats` (Base) | Season-long basic box score stats |
| `LeagueDashPlayerClutch` (Advanced) | Clutch-situation advanced stats |
| `LeagueDashPlayerClutch` (Home/Road splits) | Clutch stats split by home vs. road games |
| `LeagueDashTeamStats` (Advanced) | Team defensive ratings, by season |
| Matchup/primary defender endpoints | Player-vs-player defensive matchup minutes |
| Awards endpoint | Career awards (used to classify reputation tier) |
| `ShotChartDetail` | Individual clutch shot attempts, with location and opponent context |

## Repository Structure

```
data_eng_project/
    pipeline/
        extract/        — one module per data domain (stats, matchups, awards, shots, static)
        load/            — save/load utilities, missing-player backfill logic
        main.py          — orchestrates the full raw EL run
        load_shots.py    — separate script for shot extraction (see Architecture)
        checks.py        — data validation helpers
    dbt/
        models/          — 7 dbt models + sources.yml + schema.yml (tests & descriptions)
        dbt_project.yml
    airflow/
        docker-compose.yaml
        dags/nba_pipeline.py
    scratch/
        nba_data_load.ipynb — ad-hoc notebook for testing snippets 
    nba_schema.sql       — full raw table DDL
    nba_clutch.duckdb    — the database itself
    cached_data/         — per-table parquet cache, avoids re-hitting the API on reruns
```

## Setup & Running

**Requirements:** Python 3, DuckDB, dbt-core + dbt-duckdb, Docker Desktop.

**Run manually**, in this exact order (each stage depends on the previous one completing):
```bash
python3 pipeline/main.py       # raw extract + load — ~1h49m on a full run, all seasons
cd dbt && dbt deps --profiles-dir . && dbt build --profiles-dir .   # installs dbt_utils, then builds all 7 models and runs 12 tests
cd .. && python3 pipeline/load_shots.py   # shot extraction — requires dbt build to have completed at least once
```

**Run via Airflow** (recommended — handles the sequencing automatically):
```bash
cd airflow
docker compose up airflow-init    # one-time setup
docker compose up -d              # starts the full stack
```
Then trigger the `nba_clutch_pipeline` DAG from the UI at `localhost:8080` (default login: `airflow` / `airflow`). The DAG runs `main.py → dbt deps → dbt build → load_shots.py` in sequence, matching the dependency order above.

> Note: the Airflow environment installs project dependencies (`nba_api`, `pandas`, `duckdb`, `dbt-core`, `dbt-duckdb`) at container startup via `_PIP_ADDITIONAL_REQUIREMENTS`. This is a quick/dev-only approach — it re-installs on every container restart, which is fine for local development but not intended for production use.

## dbt Models

| Model | What it answers |
|---|---|
| `player_tier` | Classifies each player into a reputation tier — Role, Star, or Olympic Gold Medalist — based on career awards |
| `player_clutch_performance` | One row per player-season, combining season-long and clutch-situation stats, with `ts_delta` measuring clutch vs. season shooting efficiency |
| `home_vs_road` | Compares clutch performance at home vs. on the road |
| `matchup_analysis` | Per primary-defender matchup, including the defender's own season defensive rating alongside the primary player's clutch performance |
| `star_player_performance` | Subset of `player_clutch_performance` limited to Star/Olympic tier players, with each player's first award-winning season attached |
| `player_clutch_playmaking` | Adds season-long assist/rebound involvement alongside clutch scoring metrics |
| `shots_with_opponent` | Every clutch shot attempt joined to the shooter's opponent team and that opponent's season defensive rating |

All models are tested for row-level uniqueness (via `dbt_utils.unique_combination_of_columns` or `unique`/`not_null` on a surrogate key) and, where relevant, accepted-value constraints on categorical fields.

## Known Limitations & Deliberate Simplifications

- **Clutch definition is time-based, not score-based.** "Clutch" is approximated as Period ≥ 4 and ≤5 minutes remaining, without factoring in score differential — full play-by-play data would be required for a true clutch definition (last 5 minutes, game within 5 points), and wasn't pulled for this project.
- **Season range is hardcoded** to 2004-05 through 2025-26.
- **Load strategy is full-reprocess**, not incrementally extracted — every run re-checks all cached data via `INSERT OR REPLACE`, rather than only pulling genuinely new records.
- **71 of 435,943 clutch shots (0.02%)** have no recorded shot location (`loc_x`/`loc_y` are null in the source data) and were excluded when backfilling team/opponent context onto the shots table.
- **Current-season handling isn't implemented** — there's no logic to distinguish an in-progress season from a completed one, so a season fetched mid-year would be cached as if final.
