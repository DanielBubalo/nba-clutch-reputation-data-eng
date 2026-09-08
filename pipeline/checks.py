import pandas as pd


# Does a sanity check on entered table (validation)
def validation(static_table: pd.DataFrame, column_name: str) -> str:
    id_column = static_table[column_name]
    id_length = len(id_column)
    unique_ids = id_column.nunique()

    if id_length == unique_ids:
        return "Pass"
    else:
        return "Fail"


# Checks whether one table's IDs are fully contained in anothers
def check_mismatch(
    table_1: pd.DataFrame, table_2: pd.DataFrame, column_name_1: str, column_name_2: str
) -> str:
    id_set_1 = set(table_1[column_name_1])
    id_set_2 = set(table_2[column_name_2])

    if id_set_1.issubset(id_set_2):
        return "Pass"
    else:
        return "Fail"
