from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

REPO = "m1guelovski/tradingview-overlay-extension"
YEARS = [2012, 2015, 2016, 2017, 2018, 2020, 2022, 2024]
CAL_YEARS = {2012, 2016, 2018, 2022}
VAL_YEARS = set(YEARS) - CAL_YEARS
ARTIFACTS = {
    ("sequential", 2012): 9882452110,
    ("sequential", 2015): 9882450057,
    ("sequential", 2016): 9882459891,
    ("sequential", 2017): 9882461870,
    ("sequential", 2018): 9882452153,
    ("sequential", 2020): 9882452300,
    ("sequential", 2022): 9882452912,
    ("sequential", 2024): 9882452801,
    ("simultaneous", 2012): 9882393028,
    ("simultaneous", 2015): 9882394725,
    ("simultaneous", 2016): 9882394503,
    ("simultaneous", 2017): 9882394510,
    ("simultaneous", 2018): 9882392153 if False else 9882392539,
    ("simultaneous", 2020): 9882394732,
    ("simultaneous", 2022): 9882393365,
    ("simultaneous", 2024): 9882394512,
}

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stage1_aggregate"
RAW = OUT / "raw"


def dl(artifact_id: int, dest: Path) -> None:
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}/zip"
    r = requests.get(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }, timeout=120)
    r.raise_for_status()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(dest)


def read_table(path: Path) -> pd.DataFrame | None:
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        if path.suffix.lower() in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        if path.suffix.lower() == ".json":
            obj = json.loads(path.read_text())
            if isinstance(obj, list): return pd.DataFrame(obj)
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                        return pd.DataFrame(v)
    except Exception:
        return None
    return None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def find_col(cols: list[str], exact: tuple[str, ...], contains: tuple[str, ...], numeric: set[str] | None = None) -> str | None:
    m = {norm(c): c for c in cols}
    for e in exact:
        if e in m and (numeric is None or m[e] in numeric): return m[e]
    for c in cols:
        n = norm(c)
        if any(k in n for k in contains) and (numeric is None or c in numeric): return c
    return None


def strategy_id_column(df: pd.DataFrame) -> str | None:
    cols = list(map(str, df.columns))
    priority = ["strategy_id", "strategy", "spec_id", "spec", "policy_id", "policy", "name"]
    m = {norm(c): c for c in cols}
    for p in priority:
        if p in m: return m[p]
    objects = [c for c in cols if df[c].dtype == object]
    if not objects: return None
    return max(objects, key=lambda c: df[c].nunique(dropna=True))


def table_score(df: pd.DataFrame) -> int:
    cols = list(map(str, df.columns)); lower = [norm(c) for c in cols]
    score = 0
    score += 5 * int(strategy_id_column(df) is not None)
    score += 4 * int(any(any(k in c for k in ("pnl", "profit", "net_result", "expectancy")) for c in lower))
    score += 3 * int(any(any(k in c for k in ("drawdown", "max_dd", "worst")) for c in lower))
    score += 2 * int(any(any(k in c for k in ("sequence", "setup", "trade", "count", "n_")) for c in lower))
    score += int(len(df) >= 20)
    score += int(len(df) >= 100)
    return score


def choose_summary(root: Path) -> tuple[Path, pd.DataFrame]:
    options = []
    for p in root.rglob("*"):
        if not p.is_file(): continue
        df = read_table(p)
        if df is None or df.empty: continue
        sid = strategy_id_column(df)
        if sid is None: continue
        options.append((table_score(df), len(df), p, df))
    if not options:
        raise RuntimeError(f"No strategy table found under {root}")
    options.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return options[0][2], options[0][3]


def standardize(family: str, year: int, source: Path, df: pd.DataFrame) -> pd.DataFrame:
    cols = list(map(str, df.columns))
    numeric = {c for c in cols if pd.api.types.is_numeric_dtype(df[c])}
    sid = strategy_id_column(df)
    assert sid is not None
    net = find_col(cols,
        ("net_pnl", "total_net_pnl", "total_pnl", "net_profit", "profit", "pnl"),
        ("net_pnl", "total_pnl", "net_profit", "total_profit", "pnl", "profit"), numeric)
    dd = find_col(cols,
        ("max_drawdown", "max_dd", "drawdown", "worst_drawdown"),
        ("max_drawdown", "max_dd", "drawdown"), numeric)
    worst = find_col(cols,
        ("worst_sequence_pnl", "worst_pnl", "min_pnl", "worst_trade"),
        ("worst_sequence", "worst_pnl", "min_pnl", "worst_trade"), numeric)
    nseq = find_col(cols,
        ("n_sequences", "sequence_count", "n_setups", "n_trades", "trades"),
        ("n_sequences", "sequence_count", "n_setups", "trade_count", "n_trades"), numeric)
    win = find_col(cols,
        ("win_rate", "winrate", "profitable_rate"),
        ("win_rate", "winrate", "profitable"), numeric)
    ruined = find_col(cols,
        ("ruined", "blown", "failed", "failures", "n_ruined"),
        ("ruin", "blown", "failure", "failed"), numeric)
    if net is None:
        raise RuntimeError(f"Cannot identify net PnL in {source}; columns={cols}")

    out = df.copy()
    out.columns = [norm(c) for c in out.columns]
    sidn = norm(sid)
    out.insert(0, "family", family)
    out.insert(1, "year", year)
    out.insert(2, "strategy_id_std", out[sidn].astype(str))
    out.insert(3, "source_file", str(source))
    out["metric_net_pnl"] = pd.to_numeric(df[net], errors="coerce")
    out["metric_max_dd"] = pd.to_numeric(df[dd], errors="coerce").abs() if dd else np.nan
    out["metric_worst"] = pd.to_numeric(df[worst], errors="coerce") if worst else np.nan
    out["metric_n"] = pd.to_numeric(df[nseq], errors="coerce") if nseq else np.nan
    out["metric_win_rate"] = pd.to_numeric(df[win], errors="coerce") if win else np.nan
    out["metric_ruined"] = pd.to_numeric(df[ruined], errors="coerce") if ruined else 0.0
    return out


def robust_rank(all_rows: pd.DataFrame, family: str) -> pd.DataFrame:
    df = all_rows[all_rows.family == family].copy()
    metric = df[["strategy_id_std", "year", "metric_net_pnl", "metric_max_dd", "metric_worst", "metric_ruined"]]
    rows = []
    for sid, g in metric.groupby("strategy_id_std"):
        if g.year.nunique() < len(YEARS):
            continue
        by = g.set_index("year")
        pnl = by.metric_net_pnl
        dd = by.metric_max_dd.replace(0, np.nan)
        cal = pnl[pnl.index.isin(CAL_YEARS)]
        val = pnl[pnl.index.isin(VAL_YEARS)]
        ruin = by.metric_ruined.fillna(0)
        rows.append({
            "family": family,
            "strategy_id": sid,
            "years": int(g.year.nunique()),
            "total_pnl": float(pnl.sum()),
            "median_pnl": float(pnl.median()),
            "worst_year_pnl": float(pnl.min()),
            "positive_years": int((pnl > 0).sum()),
            "cal_total": float(cal.sum()),
            "cal_worst": float(cal.min()),
            "cal_positive": int((cal > 0).sum()),
            "val_total": float(val.sum()),
            "val_worst": float(val.min()),
            "val_positive": int((val > 0).sum()),
            "max_dd_across_years": float(dd.max()) if dd.notna().any() else np.nan,
            "median_return_dd": float((pnl / dd).replace([np.inf, -np.inf], np.nan).median()) if dd.notna().any() else np.nan,
            "ruin_sum": float(ruin.sum()),
        })
    rank = pd.DataFrame(rows)
    if rank.empty: return rank
    # Survival and validation dominate. PnL breaks ties.
    rank["robust_score"] = (
        -1000000.0 * (rank.ruin_sum > 0).astype(float)
        + 20000.0 * rank.val_positive
        + 10000.0 * rank.cal_positive
        + 3000.0 * rank.positive_years
        + 3.0 * rank.val_worst
        + 2.0 * rank.cal_worst
        + rank.median_pnl
        + 0.10 * rank.total_pnl
        - 0.02 * rank.max_dd_across_years.fillna(0)
    )
    return rank.sort_values(["robust_score", "val_worst", "worst_year_pnl", "total_pnl"], ascending=False)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:160]


def main() -> None:
    if OUT.exists(): shutil.rmtree(OUT)
    RAW.mkdir(parents=True)
    standardized = []
    selected_tables = []

    for (family, year), artifact in ARTIFACTS.items():
        root = RAW / f"{family}_{year}"
        dl(artifact, root)
        path, table = choose_summary(root)
        std = standardize(family, year, path, table)
        standardized.append(std)
        selected_tables.append({
            "family": family, "year": year, "artifact": artifact,
            "source": str(path.relative_to(OUT)), "rows": len(table),
            "columns": list(map(str, table.columns)),
        })

    all_rows = pd.concat(standardized, ignore_index=True, sort=False)
    all_rows.to_parquet(OUT / "stage1_standardized.parquet", index=False)
    all_rows.to_csv(OUT / "stage1_standardized.csv", index=False)
    (OUT / "selected_tables.json").write_text(json.dumps(selected_tables, indent=2), encoding="utf-8")

    rankings = []
    for family in ["sequential", "simultaneous"]:
        r = robust_rank(all_rows, family)
        r.to_csv(OUT / f"ranking_{family}.csv", index=False)
        rankings.append(r)
        marker = OUT / "markers" / family
        marker.mkdir(parents=True, exist_ok=True)
        for i, row in r.head(100).reset_index(drop=True).iterrows():
            (marker / f"rank_{i+1:03d}__{slug(row.strategy_id)}.txt").write_text(
                json.dumps(row.to_dict(), indent=2, default=str), encoding="utf-8")

    combined = pd.concat(rankings, ignore_index=True, sort=False)
    combined = combined.sort_values(["robust_score", "val_worst", "worst_year_pnl"], ascending=False)
    combined.to_csv(OUT / "ranking_combined.csv", index=False)
    top = combined.head(100)
    (OUT / "TOP100.json").write_text(top.to_json(orient="records", indent=2), encoding="utf-8")

    lines = ["# Robust stage-one family ranking", "", "Calibration years: 2012, 2016, 2018, 2022.", "Validation years: 2015, 2017, 2020, 2024.", ""]
    for family in ["sequential", "simultaneous"]:
        lines.append(f"## {family}")
        r = combined[combined.family == family].head(30)
        lines.append(r.to_markdown(index=False))
        lines.append("")
    (OUT / "RANKING.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
