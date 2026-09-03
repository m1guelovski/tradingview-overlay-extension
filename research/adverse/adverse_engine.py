from __future__ import annotations
import base64,hashlib,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
payload="".join((HERE/"phase2_payload"/f"part{i:02d}.txt").read_text().strip() for i in range(10))
source=zlib.decompress(base64.b85decode(payload))
expected="48c648b93e945c114baa1625dfafd115759dab3439950145d794267c276c7c60"
actual=hashlib.sha256(source).hexdigest()
if actual!=expected: raise RuntimeError(f"checksum mismatch: {actual}")
source=source.replace(b"times = df.index.asi8", b"times = df.index.to_numpy(dtype='datetime64[ns]').astype('int64')")
source=source.replace(b"return idx.asi8.astype(np.int64),", b"return idx.to_numpy(dtype='datetime64[ns]').astype('int64'),")
exec(compile(source,"adverse_engine_phase2.py","exec"),globals())
