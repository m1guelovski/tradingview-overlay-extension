from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from numba import njit


def load_ae(path: Path):
    spec = importlib.util.spec_from_file_location("adverse_engine_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load adverse engine from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


INNER = np.array([0.0, 1.0, 2.618, 4.236, 6.854, 11.09, 17.94, 29.03, 46.97, 76.0, 123.0, 199.0, 322.0], dtype=np.float64)
OUTER = np.array([0.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0, 55.0, 89.0, 144.0, 233.0, 377.0], dtype=np.float64)


@njit(cache=False)
def rolling_mean_std(x: np.ndarray, window: int) -> Tuple[np.ndarray, np.ndarray]:
    n = x.shape[0]
    mean = np.full(n, np.nan, dtype=np.float64)
    std = np.full(n, np.nan, dtype=np.float64)
    s = 0.0
    ss = 0.0
    for i in range(n):
        v = x[i]
        s += v
        ss += v * v
        if i >= window:
            old = x[i - window]
            s -= old
            ss -= old * old
        if i >= window - 1:
            m = s / window
            var = ss / window - m * m
            if var < 0.0 and var > -1e-14:
                var = 0.0
            mean[i] = m
            std[i] = math.sqrt(max(var, 0.0))
    return mean, std


@njit(cache=False)
def detect_activations_variable(mid_close, mid_high, mid_low, bars_back, kstd, activation_fib):
    mean, std = rolling_mean_std(mid_close, bars_back)
    n = mid_close.shape[0]
    cap = max(32, n // 100)
    idx_out = np.empty(cap, dtype=np.int64)
    side_out = np.empty(cap, dtype=np.int8)
    lower_out = np.empty(cap, dtype=np.float64)
    upper_out = np.empty(cap, dtype=np.float64)
    count = 0
    pending_exists = False
    pending_dir = 0
    pending_lower = 0.0
    pending_upper = 0.0
    pending_activation = 0.0
    rearm_bull = True
    rearm_bear = True
    for i in range(bars_back, n):
        if math.isnan(mean[i]) or math.isnan(mean[i - 1]):
            continue
        sq = std[i] * kstd
        sq_prev = std[i - 1] * kstd
        lower = mean[i] - sq
        upper = mean[i] + sq
        lower_prev = mean[i - 1] - sq_prev
        upper_prev = mean[i - 1] + sq_prev
        bull_break = mid_close[i] > upper and mid_close[i - 1] <= upper_prev
        bear_break = mid_close[i] < lower and mid_close[i - 1] >= lower_prev
        touched_center = mid_low[i] <= mean[i] and mid_high[i] >= mean[i]
        if touched_center:
            rearm_bull = True
            rearm_bear = True
        refresh_bull = pending_exists and pending_dir == 1 and touched_center and mid_close[i - 1] > upper_prev
        refresh_bear = pending_exists and pending_dir == -1 and touched_center and mid_close[i - 1] < lower_prev
        if refresh_bull:
            pending_lower = lower
            pending_upper = upper
            pending_activation = lower + (upper - lower) * activation_fib
        elif refresh_bear:
            pending_lower = lower
            pending_upper = upper
            pending_activation = upper - (upper - lower) * activation_fib
        if bull_break and rearm_bull:
            pending_exists = True
            pending_dir = 1
            pending_lower = lower
            pending_upper = upper
            pending_activation = lower + (upper - lower) * activation_fib
            rearm_bull = False
        if bear_break and rearm_bear:
            pending_exists = True
            pending_dir = -1
            pending_lower = lower
            pending_upper = upper
            pending_activation = upper - (upper - lower) * activation_fib
            rearm_bear = False
        activate = False
        if pending_exists and pending_dir == 1:
            activate = mid_high[i] >= pending_activation
        elif pending_exists and pending_dir == -1:
            activate = mid_low[i] <= pending_activation
        if activate:
            if count >= idx_out.shape[0]:
                new_n = idx_out.shape[0] * 2
                i2 = np.empty(new_n, dtype=np.int64)
                s2 = np.empty(new_n, dtype=np.int8)
                l2 = np.empty(new_n, dtype=np.float64)
                u2 = np.empty(new_n, dtype=np.float64)
                i2[:count] = idx_out[:count]
                s2[:count] = side_out[:count]
                l2[:count] = lower_out[:count]
                u2[:count] = upper_out[:count]
                idx_out, side_out, lower_out, upper_out = i2, s2, l2, u2
            idx_out[count] = i
            side_out[count] = -1 if pending_dir == 1 else 1
            lower_out[count] = pending_lower
            upper_out[count] = pending_upper
            count += 1
            pending_exists = False
            pending_dir = 0
    return idx_out[:count], side_out[:count], lower_out[:count], upper_out[:count]


@njit(cache=False)
def first_le(a, start, stop, level):
    for i in range(start, stop):
        if a[i] <= level:
            return i
    return -1


@njit(cache=False)
def first_ge(a, start, stop, level):
    for i in range(start, stop):
        if a[i] >= level:
            return i
    return -1


@dataclasses.dataclass(frozen=True)
class PathKey:
    start_band: int
    tp_back: int
    intrabar_mode: str = "adverse"


@dataclasses.dataclass
class StagePath:
    symbol: str
    sequence_id: int
    setup_start_i: int
    side: int
    stage_band: int
    entry_i: int
    exit_i: int
    entry_price: float
    exit_price: float
    per_2000_price_pnl: float
    per_2000_swap: float
    outcome: int
    is_terminal: bool


@dataclasses.dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    start_band: int
    max_band: int
    tp_back: int
    progression: str
    base_lot: float
    lot_cap: float
    target_dollars: float = 0.0


def progression_multipliers(name: str, n: int) -> np.ndarray:
    if name == "fixed":
        return np.ones(n)
    if name == "linear":
        return np.arange(1, n + 1, dtype=np.float64)
    if name == "fib":
        fib = [1.0, 2.0]
        while len(fib) < n:
            fib.append(fib[-1] + fib[-2])
        return np.array(fib[:n], dtype=np.float64)
    if name == "mild":
        vals = [1.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0]
        while len(vals) < n:
            vals.append(vals[-1] + vals[-2])
        return np.array(vals[:n], dtype=np.float64)
    if name == "sqrt":
        return np.sqrt(np.arange(1, n + 1, dtype=np.float64))
    raise ValueError(name)


def quote_usd_series(data, pair, idx):
    q = pair[3:]
    if q == "USD":
        return np.ones(len(idx))
    if q in ("AUD", "EUR", "GBP", "NZD"):
        p = q + "USD"
        s = ((data[p]["BidClose"] + data[p]["AskClose"]) * 0.5).reindex(idx).ffill().bfill()
        return s.to_numpy(dtype=np.float64)
    p = "USD" + q
    s = ((data[p]["BidClose"] + data[p]["AskClose"]) * 0.5).reindex(idx).ffill().bfill()
    return (1.0 / s).to_numpy(dtype=np.float64)


def rollover_cumulative(idx):
    ny = idx.tz_convert("America/New_York")
    flags = ((ny.hour == 17) & (ny.minute == 0)).astype(np.int8)
    mult = np.where(flags == 1, np.where(ny.weekday == 2, 3, 1), 0).astype(np.int32)
    return np.concatenate(([0], np.cumsum(mult, dtype=np.int64)))


def build_paths_for_key(ae, data, swap_rates, key, year, max_hold_days=450):
    out = {m: [] for m in range(key.start_band, 11)}
    seq_counter = {m: 0 for m in range(key.start_band, 11)}
    for symbol in ae.PAIRS_28:
        df = data[symbol]
        bid_h = df["BidHigh"].to_numpy(np.float64); bid_l = df["BidLow"].to_numpy(np.float64)
        ask_h = df["AskHigh"].to_numpy(np.float64); ask_l = df["AskLow"].to_numpy(np.float64)
        mid_c = ((df["BidClose"] + df["AskClose"]) * 0.5).to_numpy(np.float64)
        mid_h = ((df["BidHigh"] + df["AskHigh"]) * 0.5).to_numpy(np.float64)
        mid_l = ((df["BidLow"] + df["AskLow"]) * 0.5).to_numpy(np.float64)
        q_usd = quote_usd_series(data, symbol, df.index)
        roll_cum = rollover_cumulative(df.index)
        act_i, act_side, act_lo, act_hi = detect_activations_variable(mid_c, mid_h, mid_l, ae.BARS_BACK, ae.KSTD, float(INNER[key.start_band]))
        free_i = {m: ae.BARS_BACK for m in range(key.start_band, 11)}
        accepted = {m: 0 for m in range(key.start_band, 11)}
        for ai in range(len(act_i)):
            a = int(act_i[ai])
            eligible = [m for m in range(key.start_band, 11) if a >= free_i[m]]
            if not eligible:
                continue
            side = int(act_side[ai]); lo = float(act_lo[ai]); hi = float(act_hi[ai]); rng = hi - lo
            if rng <= 0:
                continue
            stop_limit_i = min(len(df), a + max_hold_days * 1440)
            entry_i = a
            full = []
            for band in range(key.start_band, 11):
                entry_level = (hi - rng * INNER[band]) if side == 1 else (lo + rng * INNER[band])
                stop_level = (hi - rng * INNER[band + 1]) if side == 1 else (lo + rng * INNER[band + 1])
                tband = max(1, band - key.tp_back)
                target_level = (hi - rng * OUTER[tband]) if side == 1 else (lo + rng * OUTER[tband])
                if entry_i >= stop_limit_i:
                    break
                if side == 1:
                    tp_i = first_ge(bid_h, entry_i + 1, stop_limit_i, target_level)
                    sl_i = first_le(bid_l, entry_i, stop_limit_i, stop_level)
                else:
                    tp_i = first_le(ask_l, entry_i + 1, stop_limit_i, target_level)
                    sl_i = first_ge(ask_h, entry_i, stop_limit_i, stop_level)
                if tp_i < 0 and sl_i < 0:
                    exit_i = stop_limit_i - 1
                    exit_price = float(df["BidClose"].iloc[exit_i] if side == 1 else df["AskClose"].iloc[exit_i])
                    outcome = 0; terminal = True
                else:
                    choose_sl = sl_i >= 0 and (tp_i < 0 or sl_i <= tp_i)
                    if choose_sl:
                        exit_i = sl_i; exit_price = stop_level; outcome = -1; terminal = band == 10
                    else:
                        exit_i = tp_i; exit_price = target_level; outcome = 1; terminal = True
                conv = float(q_usd[min(exit_i, len(q_usd)-1)])
                price_pnl = ((exit_price-entry_level) if side == 1 else (entry_level-exit_price)) * 2000.0 * conv
                roll_units = int(roll_cum[min(exit_i+1, len(roll_cum)-1)] - roll_cum[min(entry_i+1, len(roll_cum)-1)])
                col = 1 if side == 1 else 0
                swap = float(swap_rates[ae.PAIR_INDEX[symbol], col]) * roll_units
                full.append(StagePath(symbol, -1, a, side, band, entry_i, exit_i, entry_level, exit_price, price_pnl, swap, outcome, terminal))
                if outcome == 1 or outcome == 0 or terminal:
                    break
                entry_i = exit_i
            if not full:
                continue
            for max_band in eligible:
                selected = []
                for st in full:
                    if st.stage_band > max_band:
                        break
                    terminal_here = st.is_terminal or (st.stage_band == max_band and st.outcome == -1)
                    selected.append(dataclasses.replace(st, sequence_id=seq_counter[max_band], is_terminal=terminal_here))
                    if st.outcome in (0, 1) or terminal_here:
                        break
                if selected:
                    out[max_band].extend(selected)
                    free_i[max_band] = selected[-1].exit_i + 1
                    seq_counter[max_band] += 1; accepted[max_band] += 1
        print(f"paths {year} {key} {symbol}: " + ",".join(f"m{m}={accepted[m]}" for m in accepted), flush=True)
    return out


def generate_specs():
    specs = []
    for start in range(3, 10):
        for depth in (0,1,2,3,4):
            max_band = min(10, start+depth)
            for tp_back in (1,2):
                for prog in ("fixed","linear","fib","mild","sqrt"):
                    for base in (0.01,0.02):
                        for cap in (0.05,0.08,0.13,0.21):
                            if depth == 0 and (prog != "fixed" or cap != 0.05):
                                continue
                            specs.append(StrategySpec(f"seq_s{start}_m{max_band}_tp{tp_back}_{prog}_b{base:.2f}_c{cap:.2f}","sequential",start,max_band,tp_back,prog,base,cap))
                if depth > 0:
                    for base in (0.01,0.02):
                        for cap in (0.05,0.08,0.13,0.21):
                            specs.append(StrategySpec(f"seq_s{start}_m{max_band}_tp{tp_back}_recovery_b{base:.2f}_c{cap:.2f}","sequential",start,max_band,tp_back,"recovery",base,cap))
    return list({s.name:s for s in specs}.values())


def evaluate_spec(paths, spec, commission_rt=0.10):
    by_seq = {}
    for p in paths:
        by_seq.setdefault(p.sequence_id, []).append(p)
    rows=[]; pnls=[]; durations=[]; max_lots=[]; stages_used=[]
    total_price=total_swap=total_comm=total_net=0.0; wins=losses=unresolved=hard_stops=0
    for seq_id, stages in by_seq.items():
        stages.sort(key=lambda x:(x.entry_i,x.stage_band)); n=len(stages)
        mult = progression_multipliers(spec.progression,n) if spec.progression != "recovery" else np.ones(n)
        realized_loss=0.0; target0=0.0; seq_price=seq_swap=seq_comm=0.0; lots=[]
        for j,st in enumerate(stages):
            if spec.progression == "recovery":
                if j == 0:
                    lot=spec.base_lot; target0=max(1.0,max(1e-9,st.per_2000_price_pnl/0.02)*spec.base_lot)
                else:
                    lot=max(spec.base_lot,(realized_loss+target0)/max(1e-9,st.per_2000_price_pnl/0.02))
            else:
                lot=spec.base_lot*float(mult[j])
            lot=min(spec.lot_cap,lot); lot=max(0.01,math.floor(lot/0.01+0.5)*0.01); lots.append(lot)
            scale=lot/0.02; price=st.per_2000_price_pnl*scale; swap=st.per_2000_swap*scale; comm=commission_rt*scale
            net=price+swap-comm; seq_price+=price; seq_swap+=swap; seq_comm+=comm
            if net<0: realized_loss += -net
        seq_net=seq_price+seq_swap-seq_comm; last=stages[-1]; terminal_outcome=last.outcome
        if terminal_outcome==1 and seq_net>0: wins+=1
        elif terminal_outcome==0: unresolved+=1
        else: losses+=1
        if terminal_outcome==-1 and last.is_terminal: hard_stops+=1
        duration=max(0.0,(last.exit_i-stages[0].entry_i)/1440.0)
        durations.append(duration);pnls.append(seq_net);max_lots.append(max(lots));stages_used.append(n)
        total_price+=seq_price;total_swap+=seq_swap;total_comm+=seq_comm;total_net+=seq_net
        rows.append({"spec":spec.name,"sequence_id":seq_id,"symbol":stages[0].symbol,"side":stages[0].side,"start_band":spec.start_band,"max_band":spec.max_band,"tp_back":spec.tp_back,"progression":spec.progression,"base_lot":spec.base_lot,"lot_cap":spec.lot_cap,"stages":n,"max_lot":max(lots),"duration_days":duration,"terminal_outcome":terminal_outcome,"price_pnl":seq_price,"swap":seq_swap,"commission":seq_comm,"net":seq_net})
    arr=np.array(pnls);dur=np.array(durations)
    summary={"spec":spec.name,"family":spec.family,"start_band":spec.start_band,"max_band":spec.max_band,"tp_back":spec.tp_back,"progression":spec.progression,"base_lot":spec.base_lot,"lot_cap":spec.lot_cap,"sequences":len(pnls),"wins":wins,"losses":losses,"unresolved":unresolved,"hard_stops":hard_stops,"win_rate":wins/len(pnls) if pnls else np.nan,"completion_rate":(wins+losses)/len(pnls) if pnls else np.nan,"total_price_pnl":total_price,"total_swap":total_swap,"total_commission":total_comm,"total_net":total_net,"mean_net":float(arr.mean()) if len(arr) else np.nan,"median_net":float(np.median(arr)) if len(arr) else np.nan,"p05_net":float(np.quantile(arr,0.05)) if len(arr) else np.nan,"p01_net":float(np.quantile(arr,0.01)) if len(arr) else np.nan,"worst_net":float(arr.min()) if len(arr) else np.nan,"profit_factor":float(arr[arr>0].sum()/-arr[arr<0].sum()) if np.any(arr<0) else np.inf,"avg_days":float(dur.mean()) if len(dur) else np.nan,"median_days":float(np.median(dur)) if len(dur) else np.nan,"p95_days":float(np.quantile(dur,0.95)) if len(dur) else np.nan,"avg_max_lot":float(np.mean(max_lots)) if max_lots else np.nan,"max_lot_seen":float(np.max(max_lots)) if max_lots else np.nan,"avg_stages":float(np.mean(stages_used)) if stages_used else np.nan}
    return summary,rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--year",type=int,required=True);ap.add_argument("--engine",type=Path,default=Path("research/adverse/adverse_engine.py"));ap.add_argument("--cache-dir",type=Path,default=Path("research/cache/fxcm"));ap.add_argument("--output-dir",type=Path,required=True);ap.add_argument("--swap-csv",type=Path,required=True);ap.add_argument("--max-hold-days",type=int,default=450);args=ap.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True);ae=load_ae(args.engine)
    start=pd.Timestamp(f"{args.year-1}-11-01",tz="UTC");end=pd.Timestamp(f"{args.year+1}-07-31 23:59:00",tz="UTC")
    counts=ae.download_native_data(args.cache_dir,start,end);print("download",args.year,counts,flush=True)
    data=ae.load_universe(args.cache_dir,start,end);print("loaded",args.year,{p:len(data[p]) for p in ae.PAIRS_28},flush=True)
    swap_rates=ae.load_swap_rates(args.swap_csv);specs=generate_specs();keys=sorted({PathKey(s.start_band,s.tp_back) for s in specs},key=lambda x:(x.start_band,x.tp_back))
    summaries=[];sequence_sample=[]
    for kidx,key in enumerate(keys):
        print(f"geometry {kidx+1}/{len(keys)} {key}",flush=True);paths_by_max=build_paths_for_key(ae,data,swap_rates,key,args.year,args.max_hold_days)
        matching=[s for s in specs if s.start_band==key.start_band and s.tp_back==key.tp_back]
        for sidx,spec in enumerate(matching):
            summary,rows=evaluate_spec(paths_by_max[spec.max_band],spec);summary["year"]=args.year;summaries.append(summary)
            if (sidx==0 and key.start_band in (4,5,6)) or (spec.progression=="recovery" and spec.start_band in (4,5) and spec.max_band>=7 and spec.lot_cap in (0.08,0.13)):
                for r in rows:r["year"]=args.year
                sequence_sample.extend(rows)
    sdf=pd.DataFrame(summaries);sdf.to_csv(args.output_dir/f"sequential_screen_{args.year}.csv",index=False);pd.DataFrame(sequence_sample).to_parquet(args.output_dir/f"sequential_samples_{args.year}.parquet",index=False);(args.output_dir/f"specs_{args.year}.json").write_text(json.dumps([dataclasses.asdict(s) for s in specs],indent=2))
    rank=sdf[(sdf.sequences>=20)&(sdf.completion_rate>=.95)].copy();rank["robust_score"]=rank.total_net+5*rank.p05_net-.1*rank.avg_days-20*rank.hard_stops;print(rank.sort_values("robust_score",ascending=False).head(30).to_string(index=False),flush=True)


if __name__=="__main__":main()
