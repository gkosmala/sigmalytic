#!/usr/bin/env python3
"""Phase 9A: Signal-Day Trigger Rules"""
import csv, math, sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

def _safe_float(val):
    try:
        v = float(val)
        return v if math.isfinite(v) else None
    except: return None

def _safe_bool(val):
    if isinstance(val, bool): return val
    return str(val).strip().lower() in ("true","1","yes")

def _obs(r):
    dist = abs(_safe_float(r.get("distance_from_252_high_pct")) or 0.0)
    days = (_safe_float(r.get("p5_days_since_252_high")) or 0.0)/5.0
    rw   = (_safe_float(r.get("range_width_pct")) or 0.0) if _safe_bool(r.get("trading_range_detected")) else 0.0
    return max(dist+days+rw, 0.1)

def _prog(r):
    s=0.0
    pt=_safe_float(r.get("p5_price_traj_10d_pct")) or 0.0
    if pt>=5: s+=10
    elif pt>=3: s+=8
    elif pt>=1: s+=5
    elif pt>=0: s+=2
    rs=_safe_float(r.get("p5_rs_traj_10d")) or 0.0
    if rs>=10: s+=10
    elif rs>=3: s+=7
    elif rs>=0: s+=3
    u1=_safe_float(r.get("w_up1_price_eff")) or 0.0
    if u1>=3: s+=10
    elif u1>=2: s+=8
    elif u1>=1: s+=5
    elif u1>=0.3: s+=2
    d1=_safe_float(r.get("w_dn1_vol_eff")) or 0.0
    if d1>=5: s+=10
    elif d1>=2: s+=6
    elif d1>=0.5: s+=3
    return s

def _payload(r):
    mfe90=_safe_float(r.get("markup_90d_pct"))
    if mfe90 is None: return None
    mfe20=_safe_float(r.get("markup_20d_pct")) or 0.0
    mae20=_safe_float(r.get("h20_mae_pct")) or 0.0
    acc90=_safe_float(r.get("h90_direction_correct")) or 0.0
    asym=(mfe20/abs(mae20)) if (mfe20>0 and mae20<0) else 0.0
    return {
        "mfe_20d":mfe20,"mfe_90d":mfe90,"acc_90d":acc90,"asym_20d":asym,
        "h1_mfe":_safe_float(r.get("h1_mfe_pct")) or 0.0,
        "h3_mfe":_safe_float(r.get("h3_mfe_pct")) or 0.0,
        "h5_mfe":_safe_float(r.get("h5_mfe_pct")) or 0.0,
        "h10_mfe":_safe_float(r.get("h10_mfe_pct")) or 0.0,
        "h20_mfe":_safe_float(r.get("h20_mfe_pct")) or 0.0,
        "h1_dir":_safe_float(r.get("h1_direction_correct")) or 0.0,
        "h3_dir":_safe_float(r.get("h3_direction_correct")) or 0.0,
        "h5_dir":_safe_float(r.get("h5_direction_correct")) or 0.0,
    }

def _summ(bmap,min_n=5):
    out=[]
    for b,vals in sorted(bmap.items()):
        if len(vals)<min_n: continue
        n=len(vals)
        av=lambda f: round(sum(v[f] for v in vals)/n,3)
        asyms=[v["asym_20d"] for v in vals if v["asym_20d"]>0]
        out.append({"bucket":b,"n":n,"mfe20":av("mfe_20d"),"mfe90":av("mfe_90d"),
            "acc90":round(av("acc_90d")*100,2),"asym":round(sum(asyms)/len(asyms),3) if asyms else 0.0,
            "h1_mfe":av("h1_mfe"),"h3_mfe":av("h3_mfe"),"h5_mfe":av("h5_mfe"),
            "h10_mfe":av("h10_mfe"),"h20_mfe":av("h20_mfe"),
            "h1_dir":round(av("h1_dir")*100,1),"h3_dir":round(av("h3_dir")*100,1),
            "h5_dir":round(av("h5_dir")*100,1)})
    return sorted(out,key=lambda x:x["mfe90"],reverse=True)

def _print_table(title,data,min_n=5,show_early=False):
    if show_early:
        fmt="{:<50} {:>5}  mfe90={:>7.2f}%  h1={:>5.2f}%  h3={:>5.2f}%  h5={:>5.2f}%  h10={:>5.2f}%  h20={:>5.2f}%"
    else:
        fmt="{:<50} {:>5}  mfe20={:>7.2f}%  mfe90={:>7.2f}%  acc90={:>6.2f}%  asym={}"
    print(f"\n{'='*112}\n{title}\n{'='*112}")
    rows=_summ(data,min_n=min_n)
    for s in rows:
        if show_early:
            print(fmt.format(s["bucket"],s["n"],s["mfe90"],s["h1_mfe"],s["h3_mfe"],s["h5_mfe"],s["h10_mfe"],s["h20_mfe"]))
        else:
            print(fmt.format(s["bucket"],s["n"],s["mfe20"],s["mfe90"],s["acc90"],s["asym"]))
    if not rows: print("  (no buckets met minimum n)")

def _spread(data,min_n=5):
    rows=_summ(data,min_n=min_n)
    return round(rows[0]["mfe90"]-rows[-1]["mfe90"],2) if len(rows)>=2 else None

def run(csv_path):
    rows=[]
    with open(csv_path,newline="",errors="ignore") as f:
        for row in csv.DictReader(f): rows.append(row)
    print(f"Loaded {len(rows)} rows from {csv_path}")

    enriched=[]
    obs_scores,prog_scores=[],[]
    for r in rows:
        p=_payload(r)
        if p is None: continue
        o=_obs(r); pr=_prog(r)
        obs_scores.append(o); prog_scores.append(pr)
        enriched.append((r,p,o,pr))

    def quartiles(vals):
        s=sorted(vals); n=len(s)
        return s[n//4],s[n//2],s[3*n//4]
    oq1,oq2,oq3=quartiles(obs_scores)
    pq1,pq2,pq3=quartiles(prog_scores)

    def ot(v):
        if v<=oq1: return "OBS_Q1"
        if v<=oq2: return "OBS_Q2"
        if v<=oq3: return "OBS_Q3"
        return "OBS_Q4"
    def pt(v):
        if v<=pq1: return "PROG_Q1"
        if v<=pq2: return "PROG_Q2"
        if v<=pq3: return "PROG_Q3"
        return "PROG_Q4"
    def dur(d):
        if d>=180: return "DUR_180_PLUS"
        if d>=120: return "DUR_120_180"
        if d>=60:  return "DUR_60_120"
        if d>=20:  return "DUR_20_60"
        return "DUR_UNDER_20"

    g_grade=defaultdict(list); g_spring=defaultdict(list)
    g_cause=defaultdict(list); g_vol_asym=defaultdict(list)
    g_demand=defaultdict(list); g_ftft=defaultdict(list)
    g_rc=defaultdict(list); g_bhv=defaultdict(list)
    g_wed=defaultdict(list); g_relvol=defaultdict(list)
    g_er1=defaultdict(list); g_er5=defaultdict(list)
    g_abs1=defaultdict(list); g_pl=defaultdict(list)
    g_apex=defaultdict(list); g_audit=defaultdict(list)

    w_grade=defaultdict(list); w_spring=defaultdict(list)
    w_cause=defaultdict(list); w_vol_asym=defaultdict(list)
    w_demand=defaultdict(list); w_ftft=defaultdict(list)
    w_rc=defaultdict(list); w_bhv=defaultdict(list)
    w_wed=defaultdict(list); w_relvol=defaultdict(list)
    w_er1=defaultdict(list); w_er5=defaultdict(list)
    w_abs1=defaultdict(list); w_pl=defaultdict(list)
    w_apex=defaultdict(list); w_audit=defaultdict(list)
    w_dur=defaultdict(list)

    t_grade=defaultdict(list); t_spring=defaultdict(list)
    t_cause=defaultdict(list); t_vol_asym=defaultdict(list)
    t_demand=defaultdict(list); t_ftft=defaultdict(list)
    t_rc=defaultdict(list); t_bhv=defaultdict(list)
    t_wed=defaultdict(list); t_composite=defaultdict(list)
    t_early_grade=defaultdict(list); t_early_spring=defaultdict(list)
    t_early_bhv=defaultdict(list); t_early_vol=defaultdict(list)

    for r,p,o,pr in enriched:
        spd=_safe_bool(r.get("w_selling_pressure_diminishing"))
        dei=_safe_bool(r.get("w_demand_efficiency_improving"))
        days=_safe_float(r.get("p5_days_since_252_high")) or 0.0
        is_state1=spd and not dei
        is_winning=(ot(o)=="OBS_Q4" and pt(pr)=="PROG_Q4" and is_state1)
        is_target=is_winning and dur(days)=="DUR_60_120"

        grade=str(r.get("grade","")).strip() or "UNK"
        ar=_safe_float(r.get("audit_score"))
        if ar is None: ab="UNK"
        elif ar>=80: ab="AUDIT_80+"
        elif ar>=60: ab="AUDIT_60-79"
        elif ar>=40: ab="AUDIT_40-59"
        else: ab="AUDIT_<40"

        spring="SPR_Y" if _safe_bool(r.get("spring_detected")) else "SPR_N"
        cr=_safe_float(r.get("cause_score"))
        if cr is None: cb="UNK"
        elif cr>=75: cb="CAUSE_HIGH"
        elif cr>=50: cb="CAUSE_MED"
        elif cr>=25: cb="CAUSE_LOW"
        else: cb="CAUSE_MIN"

        er1b=str(r.get("er1_interpretation","")).strip() or "UNK"
        er5b=str(r.get("er5_interpretation","")).strip() or "UNK"
        abs1=str(r.get("abs1_tier_20","")).strip() or "UNK"

        va=_safe_float(r.get("vol_asymmetry_ratio"))
        if va is None: vab="UNK"
        elif va>=2.0: vab="VA_2X+"
        elif va>=1.5: vab="VA_1.5X"
        elif va>=1.0: vab="VA_1X"
        elif va>=0.5: vab="VA_NEUT"
        else: vab="VA_SUPPLY"

        dem="DEM_Y" if _safe_bool(r.get("demand_dominant")) else "DEM_N"
        ftft="FTFT_Y" if _safe_bool(r.get("w_failure_to_follow_through")) else "FTFT_N"

        rcr=_safe_float(r.get("range_contraction_pct"))
        if rcr is None: rcb="UNK"
        elif rcr>=30: rcb="RC_30+"
        elif rcr>=15: rcb="RC_15"
        elif rcr>=5:  rcb="RC_5"
        else: rcb="RC_NONE"

        plr=_safe_float(r.get("price_location_in_range"))
        if plr is None: plb="UNK"
        elif plr>=0.7: plb="LOC_TOP"
        elif plr>=0.4: plb="LOC_MID"
        elif plr>=0.2: plb="LOC_LOW"
        else: plb="LOC_BTM"

        apex="APEX_Y" if _safe_bool(r.get("apex_detected")) else "APEX_N"
        bhv=str(r.get("behavior_classification","")).strip() or "UNK"
        rvb=str(r.get("rel_volume_bucket","")).strip() or "UNK"

        d1pe=_safe_float(r.get("w_dn1_price_eff")) or 0.0
        d2pe=_safe_float(r.get("w_dn2_price_eff")) or 0.0
        d3pe=_safe_float(r.get("w_dn3_price_eff")) or 0.0
        d1ve=_safe_float(r.get("w_dn1_vol_eff")) or 0.0
        d2ve=_safe_float(r.get("w_dn2_vol_eff")) or 0.0
        d3ve=_safe_float(r.get("w_dn3_vol_eff")) or 0.0
        wc=0
        if d2pe>0 and d1pe<d2pe: wc+=1
        if d2ve>0 and d1ve<d2ve: wc+=1
        if d3pe>0 and d2pe<d3pe: wc+=1
        if d3ve>0 and d2ve<d3ve: wc+=1
        if wc>=3: wb="WED_2_STRONG"
        elif wc>=2: wb="WED_1_PARTIAL"
        else: wb="WED_0_NONE"
        if d3pe>0 and d2pe>0 and d1pe>0 and d1pe<d2pe<d3pe and d1ve<d2ve<d3ve:
            wb="WED_3_FULL"

        va=_safe_float(r.get("vol_asymmetry_ratio"))
        if va is None: vab="UNK"
        elif va>=2.0: vab="VA_2X+"
        elif va>=1.5: vab="VA_1.5X"
        elif va>=1.0: vab="VA_1X"
        elif va>=0.5: vab="VA_NEUT"
        else: vab="VA_SUPPLY"

        dem="DEM_Y" if _safe_bool(r.get("demand_dominant")) else "DEM_N"
        ftft="FTFT_Y" if _safe_bool(r.get("w_failure_to_follow_through")) else "FTFT_N"

        rcr=_safe_float(r.get("range_contraction_pct"))
        if rcr is None: rcb="UNK"
        elif rcr>=30: rcb="RC_30+"
        elif rcr>=15: rcb="RC_15"
        elif rcr>=5:  rcb="RC_5"
        else: rcb="RC_NONE"

        plr=_safe_float(r.get("price_location_in_range"))
        if plr is None: plb="UNK"
        elif plr>=0.7: plb="LOC_TOP"
        elif plr>=0.4: plb="LOC_MID"
        elif plr>=0.2: plb="LOC_LOW"
        else: plb="LOC_BTM"

        apex="APEX_Y" if _safe_bool(r.get("apex_detected")) else "APEX_N"
        bhv=str(r.get("behavior_classification","")).strip() or "UNK"
        rvb=str(r.get("rel_volume_bucket","")).strip() or "UNK"

        d1pe=_safe_float(r.get("w_dn1_price_eff")) or 0.0
        d2pe=_safe_float(r.get("w_dn2_price_eff")) or 0.0
        d3pe=_safe_float(r.get("w_dn3_price_eff")) or 0.0
        d1ve=_safe_float(r.get("w_dn1_vol_eff")) or 0.0
        d2ve=_safe_float(r.get("w_dn2_vol_eff")) or 0.0
        d3ve=_safe_float(r.get("w_dn3_vol_eff")) or 0.0
        wc=0
        if d2pe>0 and d1pe<d2pe: wc+=1
        if d2ve>0 and d1ve<d2ve: wc+=1
        if d3pe>0 and d2pe<d3pe: wc+=1
        if d3ve>0 and d2ve<d3ve: wc+=1
        if wc>=3: wb="WED_2_STRONG"
        elif wc>=2: wb="WED_1_PARTIAL"
        else: wb="WED_0_NONE"
        if d3pe>0 and d2pe>0 and d1pe>0 and d1pe<d2pe<d3pe and d1ve<d2ve<d3ve:
            wb="WED_3_FULL"

        for grp,key in [(g_grade,grade),(g_spring,spring),(g_cause,cb),
            (g_vol_asym,vab),(g_demand,dem),(g_ftft,ftft),(g_rc,rcb),
            (g_bhv,bhv),(g_wed,wb),(g_relvol,rvb),(g_er1,er1b),
            (g_er5,er5b),(g_abs1,abs1),(g_pl,plb),(g_apex,apex),(g_audit,ab)]:
            grp[key].append(p)

        if is_winning:
            for grp,key in [(w_grade,grade),(w_spring,spring),(w_cause,cb),
                (w_vol_asym,vab),(w_demand,dem),(w_ftft,ftft),(w_rc,rcb),
                (w_bhv,bhv),(w_wed,wb),(w_relvol,rvb),(w_er1,er1b),
                (w_er5,er5b),(w_abs1,abs1),(w_pl,plb),(w_apex,apex),
                (w_audit,ab),(w_dur,dur(days))]:
                grp[key].append(p)

        if is_target:
            for grp,key in [(t_grade,grade),(t_spring,spring),(t_cause,cb),
                (t_vol_asym,vab),(t_demand,dem),(t_ftft,ftft),(t_rc,rcb),
                (t_bhv,bhv),(t_wed,wb),(t_early_grade,grade),
                (t_early_spring,spring),(t_early_bhv,bhv),(t_early_vol,vab)]:
                grp[key].append(p)

            sc=0
            if spring=="SPR_Y": sc+=2
            if dem=="DEM_Y": sc+=2
            if ftft=="FTFT_Y": sc+=2
            if vab in ("VA_2X+","VA_1.5X"): sc+=1
            if rcb in ("RC_30+","RC_15"): sc+=1
            if bhv=="ACCUMULATION": sc+=1
            if wb in ("WED_2_STRONG","WED_3_FULL"): sc+=1
            if cb=="CAUSE_HIGH": sc+=1
            if grade in ("A","A+","A-"): sc+=1
            if sc>=7: t_composite["COMP_7+"].append(p)
            elif sc>=5: t_composite["COMP_5-6"].append(p)
            elif sc>=3: t_composite["COMP_3-4"].append(p)
            else: t_composite["COMP_0-2"].append(p)

    print(f"\n{'='*112}")
    print("Phase 9A: Signal-Day Trigger Rules")
    print(f"{'='*112}")

    print(f"\n{'#'*80}\nSECTION 1: FULL UNIVERSE BASELINES\n{'#'*80}")
    _print_table("Grade",g_grade)
    _print_table("Audit Score",g_audit)
    _print_table("Spring Detected",g_spring)
    _print_table("Cause Score",g_cause)
    _print_table("ER1 Interpretation",g_er1)
    _print_table("ER5 Interpretation",g_er5)
    _print_table("Volume Asymmetry",g_vol_asym)
    _print_table("Demand Dominant",g_demand)
    _print_table("Failure to Follow Through",g_ftft)
    _print_table("Range Contraction",g_rc)
    _print_table("Price Location in Range",g_pl)
    _print_table("Apex Detected",g_apex)
    _print_table("Behavioral Classification",g_bhv)
    _print_table("Wave Exhaustion Depth",g_wed)
    _print_table("Relative Volume",g_relvol)

    print(f"\n{'#'*80}\nSECTION 2: WINNING COMBO (OBS_Q4+PROG_Q4+STATE_1)\n{'#'*80}")
    _print_table("Grade",w_grade,min_n=3)
    _print_table("Audit Score",w_audit,min_n=3)
    _print_table("Spring Detected",w_spring,min_n=3)
    _print_table("Cause Score",w_cause,min_n=3)
    _print_table("ER1 Interpretation",w_er1,min_n=3)
    _print_table("ER5 Interpretation",w_er5,min_n=3)
    _print_table("Volume Asymmetry",w_vol_asym,min_n=3)
    _print_table("Demand Dominant",w_demand,min_n=3)
    _print_table("Failure to Follow Through",w_ftft,min_n=3)
    _print_table("Range Contraction",w_rc,min_n=3)
    _print_table("Price Location in Range",w_pl,min_n=3)
    _print_table("Apex Detected",w_apex,min_n=3)
    _print_table("Behavioral Classification",w_bhv,min_n=3)
    _print_table("Wave Exhaustion Depth",w_wed,min_n=3)
    _print_table("Relative Volume",w_relvol,min_n=3)
    _print_table("Duration",w_dur,min_n=3)
    print("SECTION 3: TARGET BUCKET")
    for title,data in [("Grade",t_grade),("Spring",t_spring),("Cause",t_cause),("VolAsym",t_vol_asym),("Demand",t_demand),("FTFT",t_ftft),("RangeContract",t_rc),("Behavioral",t_bhv),("WED",t_wed)]:
        _print_table(title,data,min_n=3)
    print("SECTION 4: COMPOSITE")
    _print_table("Composite",t_composite,min_n=3)
    print("SECTION 5: EARLY VELOCITY")
    _print_table("Vel/Grade",t_early_grade,min_n=3,show_early=True)
    _print_table("Vel/Spring",t_early_spring,min_n=3,show_early=True)
    _print_table("Vel/Behavioral",t_early_bhv,min_n=3,show_early=True)
    _print_table("Vel/VolAsym",t_early_vol,min_n=3,show_early=True)
    print("SPREAD SUMMARY")
    pairs=[("Grade",g_grade,w_grade,t_grade),("Spring",g_spring,w_spring,t_spring),("Cause",g_cause,w_cause,t_cause),("VolAsym",g_vol_asym,w_vol_asym,t_vol_asym),("Demand",g_demand,w_demand,t_demand),("FTFT",g_ftft,w_ftft,t_ftft),("RangeContract",g_rc,w_rc,t_rc),("Behavioral",g_bhv,w_bhv,t_bhv),("WED",g_wed,w_wed,t_wed),("Composite",None,None,t_composite)]
    winners=[]
    for label,univ,combo,tgt in pairs:
        us=_spread(univ) if univ else None
        cs=_spread(combo,min_n=3) if combo else None
        ts=_spread(tgt,min_n=3) if tgt else None
        flag="PASS" if (cs and cs>=15) else ("NOTABLE" if (cs and cs>=10) else "")
        print("  %-25s  combo=%s  tgt=%s  %s" % (label,str(round(cs,1))+"pts" if cs else "N/A",str(round(ts,1))+"pts" if ts else "N/A",flag))
        if cs and cs>=10: winners.append((label,cs))
    print("VERDICT")
    if winners:
        for label,sp in sorted(winners,key=lambda x:-x[1]):
            print("  %-25s  %.1fpts  %s" % (label,sp,"PASS" if sp>=15 else "NOTABLE"))
    else: print("  No variable met threshold.")

if __name__=="__main__":
    csv_path=sys.argv[1] if len(sys.argv)>1 else "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
