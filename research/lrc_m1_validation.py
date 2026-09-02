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

text = source.decode("utf-8")
text = text.replace(
    'times=df["DateTime"].astype("int64").to_numpy(),',
    'times=df["DateTime"].to_numpy(dtype="datetime64[ns]").astype("int64"),',
)
text = text.replace(
    'mark30 = pd.date_range(start, extension_end, freq="30min", inclusive="left").astype("int64").to_numpy()',
    'mark30 = pd.date_range(start, extension_end, freq="30min", inclusive="left").to_numpy(dtype="datetime64[ns]").astype("int64")',
)
text = text.replace(
    'if __name__ == "__main__":\n    main()',
    'if False:\n    main()',
)
exec(compile(text, "lrc_m1_validation_full.py", "exec"), globals())

fast_payload = (HERE / "payload" / "fast_eventgen.txt").read_text(encoding="utf-8").strip()
fast_source = zlib.decompress(base64.b64decode(fast_payload))
fast_expected = "b1ffcd319b31bfce2c64f953efcb75126467242066fd8c1a6dfa78103de2e4e3"
fast_actual = hashlib.sha256(fast_source).hexdigest()
if fast_actual != fast_expected:
    raise RuntimeError(f"Fast-generator checksum mismatch: {fast_actual}")
fast_text = fast_source.decode("utf-8").replace("cache=True", "cache=False")
exec(compile(fast_text, "fast_eventgen.py", "exec"), globals())

def generate_candidate_events(data, year):
    return generate_candidate_events_fast(data, year, globals())

main()
