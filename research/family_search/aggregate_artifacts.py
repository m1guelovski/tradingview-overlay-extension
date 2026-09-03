from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import requests

REPO = "m1guelovski/tradingview-overlay-extension"
ARTIFACTS = {
    "seq_2012": 9882452110,
    "seq_2015": 9882450057,
    "seq_2016": 9882459891,
    "seq_2017": 9882461870,
    "seq_2018": 9882452153,
    "seq_2020": 9882452300,
    "seq_2022": 9882452912,
    "seq_2024": 9882452801,
    "sim_2012": 9882393028,
    "sim_2015": 9882394725,
    "sim_2016": 9882394503,
    "sim_2017": 9882394510,
    "sim_2018": 9882392539,
    "sim_2020": 9882394732,
    "sim_2022": 9882393365,
    "sim_2024": 9882394512,
}

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stage1_inventory"
RAW = OUT / "raw"


def download_artifact(artifact_id: int, target: Path) -> None:
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}/zip"
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=120,
    )
    response.raise_for_status()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(target)


def read_table(path: Path) -> pd.DataFrame | None:
    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        if suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                return pd.DataFrame(obj)
            if isinstance(obj, dict):
                for value in obj.values():
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        return pd.DataFrame(value)
    except Exception:
        return None
    return None


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    RAW.mkdir(parents=True, exist_ok=True)

    inventory: list[dict] = []
    candidates: list[dict] = []

    for label, artifact_id in ARTIFACTS.items():
        target = RAW / label
        download_artifact(artifact_id, target)
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            record = {
                "artifact": label,
                "artifact_id": artifact_id,
                "path": str(path.relative_to(OUT)),
                "size": path.stat().st_size,
                "suffix": path.suffix.lower(),
            }
            table = read_table(path)
            if table is not None:
                record["rows"] = int(len(table))
                record["columns"] = list(map(str, table.columns))
                record["sample"] = table.head(2).replace({pd.NA: None}).to_dict("records")
                lowered = [str(c).lower() for c in table.columns]
                score = 0
                score += 3 * int(any(any(k in c for k in ("strategy", "spec", "policy")) for c in lowered))
                score += 2 * int(any(any(k in c for k in ("pnl", "profit", "net")) for c in lowered))
                score += 2 * int(any(any(k in c for k in ("drawdown", "max_dd", "dd")) for c in lowered))
                score += int(len(table) >= 20)
                if score >= 5:
                    candidates.append({**record, "score": score})
            inventory.append(record)

    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")
    (OUT / "candidate_tables.json").write_text(json.dumps(candidates, indent=2, default=str), encoding="utf-8")

    lines = ["# Stage 1 artifact inventory", ""]
    for row in inventory:
        lines.append(f"## {row['artifact']} — `{row['path']}`")
        lines.append(f"- Size: {row['size']}")
        if "rows" in row:
            lines.append(f"- Rows: {row['rows']}")
            lines.append(f"- Columns: `{row['columns']}`")
            lines.append(f"- Sample: `{json.dumps(row['sample'], default=str)[:2000]}`")
        lines.append("")
    (OUT / "INVENTORY.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
