from pathlib import Path
import pyarrow.parquet as pq

# Count message types
msg_types = [d.name for d in Path('../data-parquet/489FFA21').iterdir() if d.is_dir()]
print(f'Total Message Types: {len(msg_types)}')

# Sample different message types and count columns
samples = {}
for msg_type in msg_types[:5]:  # First 5 as sample
    parquet_files = list(Path(f'../data-parquet/489FFA21/{msg_type}').rglob('*.parquet'))
    if parquet_files:
        schema = pq.read_schema(parquet_files[0])
        samples[msg_type] = len(schema)
        print(f'{msg_type}: {len(schema)} columns')

# Estimate total for super table
if samples:
    avg_cols = sum(samples.values()) / len(samples)
    total_estimate = int(len(msg_types) * avg_cols)
    print(f'\n{"="*50}')
    print(f'Estimated Super-Table Schema:')
    print(f'  {len(msg_types)} message types × ~{int(avg_cols)} avg columns')
    print(f'  = ~{total_estimate} total columns')
    print(f'{"="*50}')
    print('\n⚠️  Das wäre totaler Overkill!')
