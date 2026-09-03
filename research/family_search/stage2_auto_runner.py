from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RECOVERED = ROOT / "research" / "recovered" / "sequential_portfolio_stage2.py"
AGG = ROOT / "research" / "results" / "stage1_aggregate"
OUT = ROOT / "research" / "results" / "sequential_stage2_auto"
YEARS = [2012, 2015, 2016, 2017, 2018, 2020, 2022, 2024]


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def parse_cli(source: str) -> list[dict]:
    tree = ast.parse(source)
    args = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"):
            continue
        opts = []
        for item in node.args:
            try: opts.append(ast.literal_eval(item))
            except Exception: opts.append(ast.unparse(item))
        kwargs = {}
        for kw in node.keywords:
            try: kwargs[kw.arg] = ast.literal_eval(kw.value)
            except Exception: kwargs[kw.arg] = ast.unparse(kw.value)
        args.append({"options": opts, "kwargs": kwargs})
    return args


def make_finalists() -> tuple[Path, Path]:
    ranking = pd.read_csv(AGG / "ranking_sequential.csv").head(50)
    std = pd.read_parquet(AGG / "stage1_standardized.parquet")
    ids = set(ranking.strategy_id.astype(str))
    rows = std[(std.family == "sequential") & std.strategy_id_std.astype(str).isin(ids)].copy()
    # Keep one representative parameter row per strategy; remove year-specific metrics.
    drop = {"family", "year", "source_file", "metric_net_pnl", "metric_max_dd", "metric_worst", "metric_n", "metric_win_rate", "metric_ruined"}
    param_cols = [c for c in rows.columns if c not in drop]
    reps = rows.sort_values("year").drop_duplicates("strategy_id_std")[param_cols]
    ordered = ranking[["strategy_id"]].merge(reps, left_on="strategy_id", right_on="strategy_id_std", how="left")
    json_path = OUT / "finalists.json"
    csv_path = OUT / "finalists.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    json_path.write_text(ordered.to_json(orient="records", indent=2), encoding="utf-8")
    ordered.to_csv(csv_path, index=False)
    return json_path, csv_path


def option_name(record: dict) -> str | None:
    opts = [str(x) for x in record["options"] if isinstance(x, str)]
    longs = [x for x in opts if x.startswith("--")]
    return longs[0] if longs else (opts[0] if opts else None)


def build_command(year: int, args: list[dict], finalists_json: Path, finalists_csv: Path, outdir: Path) -> list[str]:
    cmd = [sys.executable, str(RECOVERED)]
    for rec in args:
        opt = option_name(rec)
        if not opt: continue
        key = norm(opt)
        kw = rec.get("kwargs", {})
        required = bool(kw.get("required", False))
        default = kw.get("default", None)
        action = kw.get("action")
        value = None
        if "year" == key or key.endswith("_year"):
            value = str(year)
        elif "cache" in key and "dir" in key:
            value = str(ROOT / "research" / "cache" / "fxcm")
        elif "output" in key or key in {"out", "out_dir", "outdir"}:
            value = str(outdir)
        elif "swap" in key:
            value = str(ROOT / "research" / "adverse" / "swap_rates_actual_2026.csv")
        elif any(x in key for x in ("finalist", "strateg", "spec", "policy")):
            value = str(finalists_json if "json" in key or "file" in key or "path" in key else finalists_csv)
        elif "ranking" in key or "stage1" in key:
            value = str(AGG / "ranking_sequential.csv")
        elif key in {"top", "top_k", "limit", "n_strategies", "max_strategies"}:
            value = "50"
        elif "start" in key and "date" in key:
            value = f"{year}-01-01"
        elif "end" in key and "date" in key:
            value = f"{year}-12-31"
        elif required and default is None:
            raise RuntimeError(f"Unmapped required CLI option: {opt}, kwargs={kw}")
        if value is not None:
            cmd.extend([opt, value])
        elif action in {"store_true", "store_false"}:
            # Retain parser default.
            pass
    return cmd


def load_result_tables(root: Path) -> list[tuple[Path, pd.DataFrame]]:
    tables = []
    for p in root.rglob("*"):
        if not p.is_file(): continue
        try:
            if p.suffix.lower() == ".csv": df = pd.read_csv(p)
            elif p.suffix.lower() in {".parquet", ".pq"}: df = pd.read_parquet(p)
            elif p.suffix.lower() == ".json":
                obj = json.loads(p.read_text())
                if isinstance(obj, list): df = pd.DataFrame(obj)
                elif isinstance(obj, dict):
                    vals = [v for v in obj.values() if isinstance(v, list) and (not v or isinstance(v[0], dict))]
                    if not vals: continue
                    df = pd.DataFrame(vals[0])
                else: continue
            else: continue
        except Exception:
            continue
        if not df.empty:
            tables.append((p, df))
    return tables


def main() -> None:
    if not RECOVERED.exists(): raise SystemExit(f"Missing recovered script: {RECOVERED}")
    if not (AGG / "ranking_sequential.csv").exists(): raise SystemExit("Missing stage-one aggregate")
    OUT.mkdir(parents=True, exist_ok=True)
    source = RECOVERED.read_text(encoding="utf-8")
    cli = parse_cli(source)
    (OUT / "cli.json").write_text(json.dumps(cli, indent=2), encoding="utf-8")
    finalists_json, finalists_csv = make_finalists()

    diagnostics = []
    for year in YEARS:
        year_out = OUT / str(year)
        year_out.mkdir(parents=True, exist_ok=True)
        cmd = build_command(year, cli, finalists_json, finalists_csv, year_out)
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3300)
        (year_out / "run.log").write_text(proc.stdout, encoding="utf-8")
        diagnostics.append({"year": year, "returncode": proc.returncode, "command": cmd, "tail": proc.stdout[-4000:]})
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    failures = [d for d in diagnostics if d["returncode"] != 0]
    if failures:
        raise SystemExit(f"Stage-two runner failures: {[d['year'] for d in failures]}")

    # Standardize every strategy-like output table and aggregate robustly.
    all_rows = []
    inventory = []
    for year in YEARS:
        for path, df in load_result_tables(OUT / str(year)):
            cols = [norm(c) for c in df.columns]
            inventory.append({"year": year, "path": str(path.relative_to(OUT)), "rows": len(df), "columns": list(map(str, df.columns))})
            id_candidates = [c for c in df.columns if any(k in norm(c) for k in ("strategy", "spec", "policy", "name"))]
            pnl_candidates = [c for c in df.columns if any(k in norm(c) for k in ("net_pnl", "total_pnl", "net_profit", "profit")) and pd.api.types.is_numeric_dtype(df[c])]
            dd_candidates = [c for c in df.columns if any(k in norm(c) for k in ("drawdown", "max_dd")) and pd.api.types.is_numeric_dtype(df[c])]
            if not id_candidates or not pnl_candidates: continue
            sid = id_candidates[0]; pnl = pnl_candidates[0]
            dd = dd_candidates[0] if dd_candidates else None
            tmp = pd.DataFrame({
                "year": year,
                "strategy_id": df[sid].astype(str),
                "net_pnl": pd.to_numeric(df[pnl], errors="coerce"),
                "max_dd": pd.to_numeric(df[dd], errors="coerce").abs() if dd else np.nan,
                "source": str(path.relative_to(OUT)),
            })
            all_rows.append(tmp)
    (OUT / "output_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    if not all_rows:
        raise SystemExit("No stage-two result table could be standardized")
    results = pd.concat(all_rows, ignore_index=True)
    results.to_csv(OUT / "stage2_standardized.csv", index=False)
    rows = []
    for sid, g in results.groupby("strategy_id"):
        # If multiple tables report the same strategy/year, use the table with the largest absolute PnL only once.
        g = g.sort_values("source").drop_duplicates("year")
        if g.year.nunique() < len(YEARS): continue
        pnl = g.set_index("year").net_pnl
        dd = g.set_index("year").max_dd
        val = pnl[pnl.index.isin({2015, 2017, 2020, 2024})]
        cal = pnl[pnl.index.isin({2012, 2016, 2018, 2022})]
        rows.append({
            "strategy_id": sid,
            "total_pnl": pnl.sum(),
            "median_pnl": pnl.median(),
            "worst_year_pnl": pnl.min(),
            "positive_years": int((pnl > 0).sum()),
            "val_total": val.sum(),
            "val_worst": val.min(),
            "val_positive": int((val > 0).sum()),
            "cal_total": cal.sum(),
            "cal_worst": cal.min(),
            "max_dd": dd.max(),
        })
    rank = pd.DataFrame(rows)
    if rank.empty: raise SystemExit("No complete stage-two strategies across all years")
    rank["score"] = 20000 * rank.val_positive + 10000 * rank.positive_years + 5 * rank.val_worst + 2 * rank.worst_year_pnl + rank.median_pnl + 0.1 * rank.total_pnl - 0.02 * rank.max_dd.fillna(0)
    rank = rank.sort_values(["score", "val_worst", "worst_year_pnl", "total_pnl"], ascending=False)
    rank.to_csv(OUT / "ranking_stage2.csv", index=False)
    marker = OUT / "markers"
    marker.mkdir(exist_ok=True)
    for i, row in rank.head(50).reset_index(drop=True).iterrows():
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", row.strategy_id)[:160]
        (marker / f"rank_{i+1:03d}__{slug}.txt").write_text(json.dumps(row.to_dict(), indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
