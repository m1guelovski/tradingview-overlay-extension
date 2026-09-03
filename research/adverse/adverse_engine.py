from __future__ import annotations
import base64,hashlib,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
payload="".join((HERE/"payload"/f"part{i}.txt").read_text().strip() for i in range(5))
source=zlib.decompress(base64.b85decode(payload))
expected="ae31d32d6bf78ee5f2420373c9b7b8bb466e1f8826b8f5ca2d173327a86f04e1"
actual=hashlib.sha256(source).hexdigest()
if actual!=expected: raise RuntimeError(f"checksum mismatch: {actual}")
exec(compile(source,"adverse_engine_full.py","exec"),globals())
