import pandas as pd
import duckdb
from paths import db_path

def shots_table():
    with duckdb.connect(str(db_path)) as con:
        con.sql("SELECT DISTINCT")