import pandas as pd
import duckdb
from pathlib import Path


# Saves the table of given data and writes the cache file
def save_table(df: pd.DataFrame, table_name: str) -> Path:
    cache_dir = Path(f"cached_data/{table_name}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    full_path = cache_dir / f"{table_name}.parquet"
    df.to_parquet(full_path, index=False)

    return full_path


# Loads the extracted data into staging table (nba_schema)
def load_table(table_name: str, file_path: str, columns: dict) -> None:
    renamed_columns = ", ".join(f'"{old}" AS {new}' for old, new in columns.items())

    with duckdb.connect("nba_clutch.duckdb") as con:
        con.sql(f"""INSERT INTO {table_name} SELECT {renamed_columns}
                FROM read_parquet("{file_path}")""")


# Adds backfill of data that is missing between dimension and fact tables
def find_missing_rows(
    fact_df: pd.DataFrame,
    dimension_df: pd.DataFrame,
    fact_column_id: str,
    dimension_column_id: str,
    fact_column_name: str,
) -> pd.DataFrame:

    fact_table_id = set(fact_df[fact_column_id])
    dimension_table_id = set(dimension_df[dimension_column_id])
    missing_ids = fact_table_id.difference(dimension_table_id)
    missing_rows = fact_df[fact_df[fact_column_id].isin(missing_ids)]
    df = missing_rows[[fact_column_id, fact_column_name]]
    return df


# Backills any missing fact table players into the the dimension table
def fill_missing_players(
    fact_df: pd.DataFrame,
    dimension_df: pd.DataFrame,
    fact_column_id: str,
    dimension_column_id: str,
    fact_column_name: str,
    dimension_column_name: str,
    file_name: str,
) -> pd.DataFrame:
    missing_players = find_missing_rows(
        fact_df, dimension_df, fact_column_id, dimension_column_id, fact_column_name
    )
    file_path = save_table(missing_players, file_name)
    missing_player_columns = {
        f"{fact_column_id}": "player_id",
        f"{fact_column_name}": "player_name",
    }
    rename_missing_players = {
        fact_column_id: f"{dimension_column_id}",
        fact_column_name: f"{dimension_column_name}",
    }
    missing_players_renamed = missing_players.rename(columns=rename_missing_players)
    df = pd.concat([dimension_df, missing_players_renamed])
    load_table("players", file_path, missing_player_columns)
    return df
