from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclasses.dataclass(frozen=True)
class RiskPolicy:
    name: str
    pair_stop: float = 900.0
    basket_block: float = 2000.0
    basket_unlock: float = 1500.0
    basket_cut: float = 3000.0
    portfolio_cut: float = 3500.0
    portfolio_resume: float = 3000.0
    portfolio_emergency: float = 4000.0
    daily_block_room: float = 1500.0
    daily_close_room: float = 1000.0
    normal_target: float = 1000.0
    heavy_target: float = 750.0
    close_buffer: float = 50.0
    heavy_days: int = 30
    active_progression_soft: bool = True
    active_progression_global: bool = False
    cut_mode: int = 0  # 0 daily, 1 one per episode, 2 new lower low
    cut_step: float = 500.0
    max_episode_rounds: int = 3
    second_round_same_day: bool = True


def risk_policies() -> List[RiskPolicy]:
    return [
        RiskPolicy("seqrisk_kiss3500"),
        RiskPolicy("seqrisk_kiss3750", portfolio_cut=3750.0, portfolio_emergency=4250.0),
        RiskPolicy("seqrisk_one_episode", cut_mode=1),
        RiskPolicy("seqrisk_new_low", cut_mode=2),
        RiskPolicy("seqrisk_active_global", active_progression_global=True),
        RiskPolicy("seqrisk_no_cuts", pair_stop=1e12, basket_block=1e12, basket_cut=1e12, portfolio_cut=1e12, portfolio_emergency=1e12),
        RiskPolicy("seqrisk_block_only", pair_stop=1e12, basket_cut=1e12, portfolio_emergency=1e12),
    ]


def build_ledger(sf, ae, data, swap_rates, spec_dict, year):
    allowed = {f.name for f in dataclasses.fields(sf.StrategySpec)}
    spec = sf.StrategySpec(**{k:v for k,v in spec_dict.items() if k in allowed})
    key = sf.PathKey(spec.start_band, spec.tp_back)
    paths_by_max = sf.build_paths_for_key(ae, data, swap_rates, key, year, 450)
    paths = paths_by_max[spec.max_band]
    by_seq: Dict[int, List] = {}
    for p in paths:
        by_seq.setdefault(p.sequence_id, []).append(p)
    rows=[]
    for seq_id, stages in by_seq.items():
        stages.sort(key=lambda x:(x.entry_i,x.stage_band)); n=len(stages)
        mult = sf.progression_multipliers(spec.progression,n) if spec.progression != "recovery" else np.ones(n)
        realized_loss=0.0; target0=0.0
        for j,st in enumerate(stages):
            if spec.progression == "recovery":
                if j == 0:
                    lot=spec.base_lot
                    target0=max(1.0,max(1e-9,(st.per_2000_tp_potential-0.10)/0.02)*spec.base_lot)
                else:
                    lot=max(spec.base_lot,(realized_loss+target0)/max(1e-9,(st.per_2000_tp_potential-0.10)/0.02))
            else:
                lot=spec.base_lot*float(mult[j])
            lot=min(spec.lot_cap,lot);lot=max(0.01,math.floor(lot/0.01+0.5)*0.01)
            scale=lot/0.02
            est_net=st.per_2000_price_pnl*scale+st.per_2000_swap*scale-0.10*scale
            if est_net<0:realized_loss+=-est_net
            idx=data[st.symbol].index
            rows.append({
                "seq":seq_id,"stage":j,"symbol":st.symbol,"side":st.side,"band":st.stage_band,
                "entry_ns":int(idx[st.entry_i].value),"exit_ns":int(idx[st.exit_i].value),
                "entry_price":st.entry_price,"exit_price":st.exit_price,"outcome":st.outcome,
                "terminal":int(st.is_terminal),"units":lot*100000.0,
            })
    df=pd.DataFrame(rows)
    if not df.empty:df=df.sort_values(["entry_ns","seq","stage"]).reset_index(drop=True)
    return spec,df


@njit(cache=False)
def basket_indices(base_idx, quote_idx, sym, side):
    b=int(base_idx[sym]);q=int(quote_idx[sym])
    if side==1:return b*2,q*2+1
    return b*2+1,q*2


@njit(cache=False)
def position_pnl(quote_idx,sym,side,entry,bid,ask,units,usd_row):
    conv=float(usd_row[int(quote_idx[sym])])
    if side==1:return (bid-entry)*units*conv
    return (entry-ask)*units*conv


@njit(cache=False)
def simulate_seq_portfolio(master_ns,bid,ask,bid_l,ask_h,usd,day_id,rollover_mult,swap_rates,
    base_idx,quote_idx,entry_i,exit_i,sym_a,side_a,seq_a,stage_a,entry_px,exit_px,outcome_a,terminal_a,units_a,
    start_i,end_i,initial_balance,pair_stop,basket_block,basket_unlock,basket_cut,portfolio_cut,portfolio_resume,
    portfolio_emergency,daily_block_room,daily_close_room,normal_target,heavy_target,close_buffer,heavy_days,
    active_soft,active_global,cut_mode,cut_step,max_episode_rounds,second_round_same_day):
    ntr=len(entry_i);nseq=int(np.max(seq_a))+1 if ntr else 0;nsym=bid.shape[1]
    seq_state=np.zeros(nseq,dtype=np.int8) #0 not started,1 live chain,2 ended/rejected
    maxopen=64
    p_id=np.empty(maxopen,np.int64);p_sym=np.empty(maxopen,np.int16);p_side=np.empty(maxopen,np.int8);p_seq=np.empty(maxopen,np.int32);p_stage=np.empty(maxopen,np.int16);p_entry=np.empty(maxopen);p_units=np.empty(maxopen);p_swap=np.empty(maxopen);p_open_i=np.empty(maxopen,np.int64)
    nopen=0;pos_of=np.full(ntr,-1,np.int32)
    entry_order=np.argsort(entry_i);exit_order=np.argsort(exit_i);ep=0;xp=0
    while ep<ntr and entry_i[entry_order[ep]]<start_i: ep+=1
    while xp<ntr and exit_i[exit_order[xp]]<start_i: xp+=1
    balance=initial_balance;e0=initial_balance;cycle_start=start_i;heavy=False
    peak=initial_balance;maxdd=0.0;maxopen_seen=0;daily_start=initial_balance;curday=day_id[start_i]
    round_used=0;emergency_used=0;global_block=False;basket_state=np.zeros(16,np.int8);basket_rounds=np.zeros(16,np.int8);basket_anchor=np.zeros(16)
    portfolio_episode=False;portfolio_rounds=0;portfolio_anchor=0.0
    metrics=np.zeros(27);metrics[18]=1e18
    cycles=np.full((128,6),np.nan);ncycles=0

    def mark(i,worst):
        pair=np.zeros(nsym);basket=np.zeros(16);op=0.0
        for j in range(nopen):
            s=int(p_sym[j]);side=int(p_side[j]);pxb=float(bid_l[i,s] if worst and side==1 else bid[i,s]);pxa=float(ask_h[i,s] if worst and side==-1 else ask[i,s])
            pp=position_pnl(quote_idx,s,side,p_entry[j],pxb,pxa,p_units[j],usd[i])+p_swap[j]
            pair[s]+=pp;b1,b2=basket_indices(base_idx,quote_idx,s,side);basket[b1]+=pp;basket[b2]+=pp;op+=pp
        return balance+op,pair,basket

    def close_pos(j,i,reason):
        nonlocal nopen,balance
        tid=int(p_id[j]);s=int(p_sym[j]);side=int(p_side[j]);seq=int(p_seq[j]);units=float(p_units[j])
        px=float(bid[i,s] if side==1 else ask[i,s]);pnl=position_pnl(quote_idx,s,side,p_entry[j],px,px,units,usd[i])+p_swap[j]-0.05*(units/2000.0)
        balance+=pnl;metrics[11]-=0.05*(units/2000.0);pos_of[tid]=-1
        if reason!=0: seq_state[seq]=2;metrics[10]+=1
        last=nopen-1
        if j!=last:
            p_id[j]=p_id[last];p_sym[j]=p_sym[last];p_side[j]=p_side[last];p_seq[j]=p_seq[last];p_stage[j]=p_stage[last];p_entry[j]=p_entry[last];p_units[j]=p_units[last];p_swap[j]=p_swap[last];p_open_i[j]=p_open_i[last];pos_of[int(p_id[j])]=j
        nopen-=1
        return pnl

    def close_all(i,reason):
        nonlocal nopen
        while nopen>0:close_pos(nopen-1,i,reason)

    def cut_round(i,bidx):
        closed=0
        for s in range(nsym):
            best=-1;bestp=0.0
            for j in range(nopen):
                if int(p_sym[j])!=s:continue
                b1,b2=basket_indices(base_idx,quote_idx,s,int(p_side[j]))
                if b1!=bidx and b2!=bidx:continue
                pp=position_pnl(quote_idx,s,int(p_side[j]),p_entry[j],float(bid[i,s]),float(ask[i,s]),p_units[j],usd[i])kp_swap[j]-0.05*(p_units[j]/2000.0)
                if pp<bestp:bestp=pp;best=j
            if best>=0:close_pos(best,i,2);closed+=1
        return closed

    for i in range(start_i,end_i):
        if day_id[i]!=curday:
            curday=day_id[i];daily_start=balance;round_used=0;emergency_used=0
        mult=int(rollover_mult[i])
        if mult>0:
            for j in range(nopen):
                s=int(p_sym[j]);col=1 if p_side[j]==1 else 0;p_swap[j]+=swap_rates[s]tÎ∑!jª-ÆÈ‹j◊ù