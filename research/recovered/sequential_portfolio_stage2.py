from __future__ import annotations

import base64
import hashlib
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
payload_dir = HERE / "sequential_portfolio_stage2_payload"
payload = "".join((payload_dir / f"part{i}.txt").read_text(encoding="utf-8").strip() for i in range(2))
source = zlib.decompress(base64.b85decode(payload))
expected = "2be0506e8c9994edbe9bd0e3c1004bdc405d8c1d27eda3fcf595fc5b65eab12e"
actual = hashlib.sha256(source).hexdigest()
if actual != expected:
    raise RuntimeError(f"Sequential stage-two checksum mismatch: {actual}")
exec(compile(source, "sequential_portfolio_stage2_full.py", "exec"), globals())
