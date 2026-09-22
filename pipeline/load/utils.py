import pandas as pd
import duckdb
from pathlib import Path
from paths import cached_data_dir, db_path


# Saves the table of given data and writes the cache file
def save_table(df: pd.DataFrame, table_name: str) -> Path:
    cache_dir = cached_data_dir / table_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    full_path = cache_dir / f"{table_name}.parquet"
    df.to_parquet(full_path, index=False)

    return full_path


# Loads the extracted data into staging table (nba_schema)
def load_table(table_name: str, file_path: str, columns: dict) -> None:
    column_list = ", ".join(f'"{col}"' for col in columns)

    with duckdb.connect(db_path) as con:
        con.sql(
            f"""INSERT OR REPLACE INTO {table_name} ({column_list}) SELECT {column_list}
                FROM read_parquet("{file_path}")"""
        )


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
    unique_df = df.drop_duplicates()
    return unique_df


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
    rename_missing_players = {
        fact_column_id: f"{dimension_column_id}",
        fact_column_name: f"{dimension_column_name}",
    }
    missing_players_renamed = missing_players.rename(columns=rename_missing_players)
    file_path = save_table(missing_players_renamed, file_name)
    df = pd.concat([dimension_df, missing_players_renamed])
    load_table("players", file_path, [dimension_column_id, dimension_column_name])
    return df
