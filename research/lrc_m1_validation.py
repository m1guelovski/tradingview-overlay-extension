from __future__ import annotations

import base64
import hashlib
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
payload = "".join(
    (HERE / "payload" / f"part{i}.txt").read_text(encoding="utf-8").strip()
    for i in range(4)
)
source = zlib.decompress(base64.b64decode(payload))
expected = "0ce3ed28f31d121c3fa8e402675d63ea0e148a4bdafadbbbf490537ad73858f4"
actual = hashlib.sha256(source).hexdigest()
if actual != expected:
    raise RuntimeError(f"Validation payload checksum mismatch: {actual}")

exec(compile(source, "lrc_m1_validation_full.py", "exec"), globals())
