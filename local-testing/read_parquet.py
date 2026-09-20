import pyarrow.parquet as pq
import pandas as pd
from pathlib import Path
import sys

# Sicherstellen, dass modules gefunden wird
sys.path.insert(0, str(Path(__file__).parent.parent))

# Einfachste Variante - eine Datei lesen
file = Path(__file__).parent.parent / "data-parquet" / "489FFA21" / "CAN1_Motor_04" / "2025" / "12" / "11" / "00000046_00000002.parquet"
df = pq.read_table(file).to_pandas()
print("=== Basis DataFrame ===")
print(df.head())
print(f"\nColumns: {df.columns.tolist()}\n")

# Oder mit der Repo-Funktion (mit Timestamp-Index):
from modules.utils import load_parquet_to_df
df = load_parquet_to_df(file, "CAN1_Motor_04")
print("\n=== Mit load_parquet_to_df (Timestamp als Index) ===")
print(df.head())
print(f"\nIndex: {df.index.name}")
print(f"Columns: {df.columns.tolist()}")

# Alle Motor-Daten kombinieren:
motor_files = (Path(__file__).parent.parent / "data-parquet" / "489FFA21" / "CAN1_Motor_04").rglob("*.parquet")
dfs = [pq.read_table(f).to_pandas() for f in motor_files]
df_all = pd.concat(dfs, ignore_index=True)
print(f"\n=== Kombiniert {len(dfs)} Dateien ===")
print(f"Total rows: {len(df_all)}")
print(df_all.head())