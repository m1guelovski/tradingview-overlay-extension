from __future__ import annotations

import gzip
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

OUT = Path('research/output')
OUT.mkdir(parents=True, exist_ok=True)

url = 'https://candledata.fxcorporate.com/m1/EURGBP/2018/7.csv.gz'
r = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
print('status', r.status_code, 'bytes', len(r.content), 'type', r.headers.get('content-type'))
r.raise_for_status()
raw = gzip.decompress(r.content)
print(raw[:500].decode('utf-8', errors='replace'))
(OUT / 'probe.csv').write_bytes(raw)
df = pd.read_csv(BytesIO(raw))
print(df.head())
print(df.columns.tolist(), len(df))
(OUT / 'probe_summary.txt').write_text(f'url={url}\nrows={len(df)}\ncolumns={df.columns.tolist()}\n', encoding='utf-8')
