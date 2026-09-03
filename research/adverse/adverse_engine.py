from __future__ import annotations
import base64,hashlib,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
payload="".join((HERE/"phase2_payload"/f"part{i:02d}.txt").read_text().strip() for i in range(10))
source=zlib.decompress(base64.b85decode(payload))
expected="48c648b93e945c114baa1625dfafd115759dab3439950145d794267c276c7c60"
actual=hashlib.sha256(source).hexdigest()
if actual!=expected: raise RuntimeError(f"checksum mismatch: {actual}")
exec(compile(source,"adverse_engine_phase2.py","exec"),globals())
