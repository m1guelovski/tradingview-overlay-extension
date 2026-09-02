from __future__ import annotations

import base64
import hashlib
import zlib
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
payload = "".join(
    (HERE / "payload" / f"part{i}.txt").read_text(encoding="utf-8").strip()
    for i in range(4)
)
source = zlib.decompress(base64.b64decode(payload))
expected = "0ce3ed28f31d121c3fa8e402675d63ea0e148a4bdafadbbbf490537ad73858f4"
actual = hashlib.sha256(source).hexdigest()
if actual != expected:
    raise RuntimeError(f"Payload checksum mismatch: {actual}")

text = source.decode("utf-8")
text = text.replace(
    'times=df["DateTime"].astype("int64").to_numpy(),',
    'times=df["DateTime"].to_numpy(dtype="datetime64[ns]").astype("int64"),',
)
text = text.replace(
    'mark30 = pd.date_range(start, extension_end, freq="30min", inclusive="left").astype("int64").to_numpy()',
    'mark30 = pd.date_range(start, extension_end, freq="30min", inclusive="left").to_numpy(dtype="datetime64[ns]").astype("int64")',
)
text = text.replace('if __name__ == "__main__":\n    main()', 'if False:\n    main()')
exec(compile(text, "lrc_core.py", "exec"), globals())

out = HERE / "output2026"
out.mkdir(parents=True, exist_ok=True)
bundle_file = BUNDLES / "bundle_2026.pkl.gz"
if bundle_file.exists():
    bundle_file.unlink()

bundle = build_year_bundle(2026)
start = int(pd.Timestamp("2026-06-18 00:00:00", tz="UTC").value)
end = int(pd.Timestamp("2026-08-01 00:00:00", tz="UTC").value)

columns = [
    "position_id", "setup_id", "symbol", "side", "label", "tier",
    "setup_start", "entry_time", "entry_price", "target",
    "natural_exit_time", "natural_exit_price", "forced_end",
]
rows = []
for cp in bundle.candidates.values():
    if start <= cp.entry_ns < end:
        rows.append({
            "position_id": cp.position_id,
            "setup_id": cp.setup_id,
            "symbol": cp.symbol,
            "side": cp.side,
            "label": cp.label,
            "tier": cp.tier,
            "setup_start": pd.Timestamp(cp.setup_start_ns, tz="UTC"),
            "entry_time": pd.Timestamp(cp.entry_ns, tz="UTC"),
            "entry_price": cp.entry_price,
            "target": cp.target,
            "natural_exit_time": pd.Timestamp(cp.natural_exit_ns, tz="UTC"),
            "natural_exit_price": cp.natural_exit_price,
            "forced_end": cp.forced_end,
        })

cand = pd.DataFrame(rows, columns=columns)
if not cand.empty:
    cand = cand.sort_values(["entry_time", "symbol", "label"])
cand.to_csv(out / "candidate_entries_2026.csv", index=False)

coverage = pd.DataFrame(bundle.coverage)
setups = pd.DataFrame(bundle.setup_summary)
coverage.to_csv(out / "coverage_2026.csv", index=False)
setups.to_csv(out / "setups_2026.csv", index=False)

all_entry_ns = [cp.entry_ns for cp in bundle.candidates.values()]
all_setup_ns = [s.get("start_ns") for s in bundle.setup_summary if s.get("start_ns") is not None]
summary = [
    f"candidate_entries_jun18_jul31={len(rows)}",
    f"all_candidates={len(bundle.candidates)}",
    f"all_events={len(bundle.events)}",
    f"all_setups={len(bundle.setup_summary)}",
    f"coverage_ok={(coverage.status == 'ok').sum() if 'status' in coverage else 0}",
]
if all_entry_ns:
    summary += [
        f"candidate_min={pd.Timestamp(min(all_entry_ns), tz='UTC')}",
        f"candidate_max={pd.Timestamp(max(all_entry_ns), tz='UTC')}",
    ]
if all_setup_ns:
    summary += [
        f"setup_min={pd.Timestamp(min(all_setup_ns), tz='UTC')}",
        f"setup_max={pd.Timestamp(max(all_setup_ns), tz='UTC')}",
    ]
if not coverage.empty:
    for _, row in coverage.iterrows():
        summary.append(
            f"coverage:{row.get('symbol')}:{row.get('status')}:rows={row.get('rows')}:"
            f"first={row.get('first')}:last={row.get('last')}:setups={row.get('setups')}:candidates={row.get('candidate_positions')}"
        )

(out / "summary_2026.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
print((out / "summary_2026.txt").read_text(), flush=True)
