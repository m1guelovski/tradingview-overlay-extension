from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def load_ae(path: Path):
    spec = importlib.util.spec_from_file_location("adverse_engine_runtime2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclasses.dataclass(frozen=True)
class Variant:
    name: str
    keep_slots: Tuple[int, ...] = (0,1,2,3,4,5)
    allow_reentry_tiers: Tuple[int, ...] = (4,5,6)
    policy_overrides: Tuple[Tuple[str, object], ...] = ()
    def policy(self, ae):
        return ae.Policy(name=self.name, **{k:v for k,v in self.policy_overrides})


def ov(**kwargs): return tuple(sorted(kwargs.items()))


def variants() -> List[Variant]:
    v=[]
    def add(name,slots=(0,1,2,3,4,5),re_tiers=(4,5,6),**kwargs):
        v.append(Variant(name,tuple(slots),tuple(re_tiers),ov(**kwargs)))
    add("sim_current_123")
    add("sim_current_no_reentry",max_reentries_per_candidate_setup=0)
    add("sim_current_reentry_cap1",max_reentries_per_candidate_setup=1)
    add("sim_current_reentry_cap3",max_reentries_per_candidate_setup=3)
    add("sim_current_reentry_cap5",max_reentries_per_candidate_setup=5)
    add("sim_current_reentry_age3",reentry_age_days=3)
    add("sim_current_reentry_age7",reentry_age_days=7)
    add("sim_current_reentry_age14",reentry_age_days=14)
    add("sim_current_reentry_only_b6",re_tiers=(6,))
    add("sim_current_no_b4_reentry",re_tiers=(5,6))
    add("sim_111_near",slots=(0,1,3))
    add("sim_111_deep",slots=(0,2,5))
    add("sim_112_near_deep",slots=(0,2,3,5))
    add("sim_122",slots=(0,1,2,3,5))
    add("sim_113",slots=(0,2,3,4,5))
    add("sim_start_b5_23",slots=(1,2,3,4,5),re_tiers=(5,6))
    add("sim_start_b5_13",slots=(2,3,4,5),re_tiers=(5,6))
    add("sim_b6_only_3",slots=(3,4,5),re_tiers=(6,))
    add("sim_b6_one_near",slots=(3,),re_tiers=(6,))
    add("sim_b6_one_deep",slots=(5,),re_tiers=(6,))
    add("sim_b4_b6",slots=(0,3,4,5),re_tiers=(4,6))
    add("sim_all_001",units_b4=1000.0,units_b5=1000.0,units_b6=1000.0)
    add("sim_deep_weight_001_001_002",units_b4=1000.0,units_b5=1000.0,units_b6=2000.0)
    add("sim_deep_weight_001_002_002",units_b4=1000.0,units_b5=2000.0,units_b6=2000.0)
    add("sim_progressive_001_002_003",units_b4=1000.0,units_b5=2000.0,units_b6=3000.0)
    add("sim_progressive_001_001_003",units_b4=1000.0,units_b5=1000.0,units_b6=3000.0)
    add("sim_all_003",units_b4=3000.0,units_b5=3000.0,units_b6=3000.0)
    add("sim_b5_b6_001_002",slots=(1,2,3,4,5),re_tiers=(5,6),units_b5=1000.0,units_b6=2000.0)
    add("sim_b6_only_002",slots=(3,4,5),re_tiers=(6,),units_b6=2000.0)
    add("sim_b6_only_003",slots=(3,4,5),re_tiers=(6,),units_b6=3000.0)
    add("sim_123_plus_b7_001",slots=(0,1,2,3,4,5,6),re_tiers=(4,5,6,7),include_b7=True,b7_slots=1,units_b7=1000.0)
    add("sim_123_plus_b7_002",slots=(0,1,2,3,4,5,6),re_tiers=(4,5,6,7),include_b7=True,b7_slots=1,units_b7=2000.0)
    add("sim_b5_b6_b7",slots=(1,2,3,4,5,6),re_tiers=(5,6,7),include_b7=True,b7_slots=1,units_b7=1000.0)
    add("sim_soft_initial_completion",active_completion_mode=1)
    add("sim_soft_no_completion",active_completion_mode=0)
    add("sim_global_initial_completion",global_completion_mode=1)
    add("sim_one_episode_cuts",cut_cadence_mode=1,second_round_same_day=True)
    add("sim_new_lower_low_cuts",cut_cadence_mode=2,cut_step=500.0,max_episode_rounds=3)
    add("sim_b4_first_cuts",cut_mode=1)
    add("sim_relief_cuts",cut_mode=2)
    add("sim_portfolio_3250",portfolio_cut=3250.0,portfolio_resume=2750.0,portfolio_emergency=3750.0)
    add("sim_portfolio_3750",portfolio_cut=3750.0,portfolio_resume=3000.0,portfolio_emergency=4250.0)
    add("sim_portfolio_4000",portfolio_cut=4000.0,portfolio_resume=3250.0,portfolio_emergency=4400.0)
    add("sim_basket_1500_2500",basket_block=1500.0,basket_unlock=1200.0,basket_cut=2500.0)
    add("sim_basket_2500_3500",basket_block=2500.0,basket_unlock=1900.0,basket_cut=3500.0)
    add("sim_pair_600",pair_stop=600.0)
    add("sim_pair_750",pair_stop=750.0)
    add("sim_pair_1050",pair_stop=1050.0)
    add("sim_heavy_half_size",heavy_units_factor=0.5)
    add("sim_dd_half_size_2500",dd_reduce_start=2500.0,dd_units_factor=0.5)
    add("sim_soft_basket_half_size",soft_basket_units_factor=0.5)
    add("sim_exposure_taper_12",basket_exposure_soft=12.0,exposure_units_factor=0.5,basket_exposure_hard=20.0)
    add("sim_exposure_cap_16",basket_exposure_soft=12.0,exposure_units_factor=0.5,basket_exposure_hard=16.0)
    add("sim_rotation_stale_b5_7",rotation_mode=1,rotation_age_days=7,rotation_max_victims=1)
    add("sim_rotation_stale_b4_7",rotation_mode=2,rotation_age_days=7,rotation_max_victims=1)
    add("sim_rotation_worst_7",rotation_mode=3,rotation_age_days=7,rotation_max_victims=1)
    add("sim_rotation_oldest_7",rotation_mode=4,rotation_age_days=7,rotation_max_victims=1)
    add("sim_heavy_25_600",heavy_days=25,heavy_positions=120,heavy_target=600.0)
    add("sim_heavy_30_600",heavy_days=30,heavy_positions=120,heavy_target=600.0)
    add("sim_heavy_30_1000",heavy_days=30,heavy_positions=120,heavy_target=1000.0)
    add("sim_heavy_40_750",heavy_days=40,heavy_positions=150,heavy_target=750.0)
    return v


def filtered_arrays(arrays: Dict[str,np.ndarray],variant: Variant):
    local=dict(arrays);e=arrays["entry_i"].copy();slot=arrays["slot"];tier=arrays["tier"];re=arrays["reentry_seq"]
    mask=np.isin(slot,np.array(variant.keep_slots,dtype=slot.dtype)) & ((re==0)|np.isin(tier,np.array(variant.allow_reentry_tiers,dtype=tier.dtype)))
    e[~mask]=len(arrays["master_ns"])+10;local["entry_i"]=e;return local


def selected_starts(ae,year):
    starts=ae.scenario_starts(year);starts.extend(pd.Timestamp(f"{year}-{m:02d}-01",tz="UTC") for m in (2,5,8,11));return sorted(set(starts))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--year",type=int,required=True);ap.add_argument("--engine",type=Path,default=Path("research/adverse/adverse_engine.py"));ap.add_argument("--cache-dir",type=Path,default=Path("research/cache/fxcm"));ap.add_argument("--output-dir",type=Path,required=True);ap.add_argument("--swap-csv",type=Path,required=True);ap.add_argument("--horizon-days",type=int,default=300);args=ap.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True);ae=load_ae(args.engine);starts=selected_starts(ae,args.year);data_end=max(starts)+pd.Timedelta(days=args.horizon_days+7)
    arrays=ae.prepare_year(args.year,args.cache_dir,args.output_dir,args.swap_csv,include_b7_candidates=True,allow_same_bar_deep=True,data_end=data_end)
    rows=[];cycles=[];vv=variants()
    for vi,var in enumerate(vv):
        pol=var.policy(ae);arr=filtered_arrays(arrays,var);master=arr["master_ns"]
        for si,st in enumerate(starts):
            en=min(st+pd.Timedelta(days=args.horizon_days),pd.Timestamp(master[-1],tz="UTC"));m,cy,_=ae.run_policy(pol,arr,int(st.value),int(en.value));md=ae.metrics_dict(m)
            rows.append({"year":args.year,"variant":var.name,"scenario":si,"start":str(st),"end":str(en),"slots":"-".join(map(str,var.keep_slots)),"reentry_tiers":"-".join(map(str,var.allow_reentry_tiers)),**md})
            for ci,c in enumerate(cy):cycles.append({"year":args.year,"variant":var.name,"scenario":si,"cycle":ci,"profit":c[1],"days":c[2],"heavy":c[3],"max_dd":c[4],"max_open":c[5]})
        print(f"variant {args.year} {vi+1}/{len(vv)} {var.name}",flush=True)
    pd.DataFrame(rows).to_csv(args.output_dir/f"simultaneous_results_{args.year}.csv",index=False);pd.DataFrame(cycles).to_csv(args.output_dir/f"simultaneous_cycles_{args.year}.csv",index=False);(args.output_dir/f"simultaneous_variants_{args.year}.json").write_text(json.dumps([dataclasses.asdict(x) for x in vv],indent=2,default=str))

if __name__=="__main__":main()
