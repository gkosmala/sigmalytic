#!/usr/bin/env python3
"""
Phase 9C: Behavioral Confirmation Layer
Tests the five Track D behavioral metrics from the Phase 9 addendum:
  D1: Failure-to-decline score (FTFT proxy)
  D2: Recovery speed score
  D3: Volume acceptance score (vol_asymmetry_ratio)
  D4: Gap acceptance score
  D5: Range compression score (range_contraction_pct)

All metrics computed from pre-signal data already in the dataset.
No new data required.

Pass condition: composite behavioral confirmation score produces
>= 20 mfe90 point spread inside the target bucket.
"""
import csv, math, sys
from collections import defaultdict

def _f(val):
    try:
        v=float(val)
        return v if math.isfinite(v) else None
    except: return None

def _b(val):
    if isinstance(val,bool): return val
    return str(val).strip().lower() in ("true","1","yes")

def _obs(r):
    dist=abs(_f(r.get("distance_from_252_high_pct")) or 0.0)
    days=(_f(r.get("p5_days_since_252_high")) or 0.0)/5.0
    rw=(_f(r.get("range_width_pct")) or 0.0) if _b(r.get("trading_range_detected")) else 0.0
    return max(dist+days+rw,0.1)

def _prog(r):
    s=0.0
    pt=_f(r.get("p5_price_traj_10d_pct")) or 0.0
    if pt>=5: s+=10
    elif pt>=3: s+=8
    elif pt>=1: s+=5
    elif pt>=0: s+=2
    rs=_f(r.get("p5_rs_traj_10d")) or 0.0
    if rs>=10: s+=10
    elif rs>=3: s+=7
    elif rs>=0: s+=3
    u1=_f(r.get("w_up1_price_eff")) or 0.0
    if u1>=3: s+=10
    elif u1>=2: s+=8
    elif u1>=1: s+=5
    elif u1>=0.3: s+=2
    d1=_f(r.get("w_dn1_vol_eff")) or 0.0
    if d1>=5: s+=10
    elif d1>=2: s+=6
    elif d1>=0.5: s+=3
    return s

def _pay(r):
    mfe90=_f(r.get("markup_90d_pct"))
    if mfe90 is None: return None
    mfe20=_f(r.get("markup_20d_pct")) or 0.0
    mae20=_f(r.get("h20_mae_pct")) or 0.0
    acc90=_f(r.get("h90_direction_correct")) or 0.0
    asym=(mfe20/abs(mae20)) if (mfe20>0 and mae20<0) else 0.0
    return {"mfe90":mfe90,"mfe20":mfe20,"acc90":acc90,"asym":asym}

def _summ(bmap,min_n=5):
    out=[]
    for b,vals in sorted(bmap.items()):
        if len(vals)<min_n: continue
        n=len(vals)
        av=lambda f,v=vals,n=n:round(sum(x[f] for x in v)/n,3)
        asyms=[v["asym"] for v in vals if v["asym"]>0]
        out.append({"b":b,"n":n,"mfe90":av("mfe90"),"mfe20":av("mfe20"),
            "acc90":round(av("acc90")*100,2),
            "asym":round(sum(asyms)/len(asyms),3) if asyms else 0.0})
    return sorted(out,key=lambda x:x["mfe90"],reverse=True)

def _pt(title,data,min_n=5):
    fmt="{:<50} {:>5}  mfe20={:>7.2f}%  mfe90={:>7.2f}%  acc90={:>6.2f}%  asym={}"
    print("\n"+"="*100+"\n"+title+"\n"+"="*100)
    rows=_summ(data,min_n=min_n)
    for s in rows:
        print(fmt.format(s["b"],s["n"],s["mfe20"],s["mfe90"],s["acc90"],s["asym"]))
    if not rows: print("  (no buckets met minimum n)")

def _sp(data,min_n=5):
    rows=_summ(data,min_n=min_n)
    return round(rows[0]["mfe90"]-rows[-1]["mfe90"],2) if len(rows)>=2 else None

def run(csv_path):
    rows=[]
    with open(csv_path,newline="",errors="ignore") as f:
        for row in csv.DictReader(f): rows.append(row)
    print("Loaded %d rows from %s" % (len(rows),csv_path))

    enriched=[]
    obs_s,prog_s=[],[]
    for r in rows:
        p=_pay(r)
        if p is None: continue
        o=_obs(r); pr=_prog(r)
        obs_s.append(o); prog_s.append(pr)
        enriched.append((r,p,o,pr))

    def qq(vals):
        s=sorted(vals); n=len(s)
        return s[n//4],s[n//2],s[3*n//4]
    oq1,oq2,oq3=qq(obs_s)
    pq1,pq2,pq3=qq(prog_s)

    def ot(v):
        if v<=oq1: return "Q1"
        if v<=oq2: return "Q2"
        if v<=oq3: return "Q3"
        return "Q4"
    def pt(v):
        if v<=pq1: return "Q1"
        if v<=pq2: return "Q2"
        if v<=pq3: return "Q3"
        return "Q4"
    def dur(d):
        if d>=180: return "DUR_180+"
        if d>=120: return "DUR_120_180"
        if d>=60: return "DUR_60_120"
        if d>=20: return "DUR_20_60"
        return "DUR_UNDER_20"

    # ── Track D metric classifiers ────────────────────────────────────────────

    # D1: Failure-to-follow-through (sellers failing to press)
    def d1(r):
        return "D1_Y" if _b(r.get("w_failure_to_follow_through")) else "D1_N"

    # D3: Volume acceptance (vol asymmetry ratio — buying vs selling volume)
    def d3(r):
        va=_f(r.get("vol_asymmetry_ratio"))
        if va is None: return "D3_UNK"
        if va>=2.0: return "D3_STRONG"
        if va>=1.0: return "D3_MOD"
        if va>=0.5: return "D3_NEUTRAL"
        return "D3_SUPPLY"

    # D5: Range compression (range contracting = emotional volatility subsiding)
    def d5(r):
        rc=_f(r.get("range_contraction_pct"))
        if rc is None: return "D5_UNK"
        if rc>=30: return "D5_STRONG"
        if rc>=15: return "D5_MOD"
        if rc>=5: return "D5_SLIGHT"
        return "D5_NONE"

    # Demand dominant (combines D1+D3 concept)
    def dd(r):
        return "DD_Y" if _b(r.get("demand_dominant")) else "DD_N"

    # Springboard (structural confirmation of absorption)
    def sp(r):
        return "SP_Y" if _b(r.get("w_springboard_present")) else "SP_N"

    # Cause score (accumulated structural cause)
    def cs(r):
        c=_f(r.get("cause_score"))
        if c is None: return "CS_UNK"
        if c>=75: return "CS_HIGH"
        if c>=50: return "CS_MED"
        if c>=25: return "CS_LOW"
        return "CS_MIN"

    # Behavioral classification
    def bhv(r):
        return str(r.get("behavior_classification","")).strip() or "UNK"

    # ── Track D composite score ───────────────────────────────────────────────
    def d_score(r):
        score=0
        # D1: failure to follow through (+2 — strongest behavioral signal)
        if _b(r.get("w_failure_to_follow_through")): score+=2
        # D3: volume acceptance (+2)
        va=_f(r.get("vol_asymmetry_ratio")) or 0.0
        if va>=2.0: score+=2
        elif va>=1.0: score+=1
        # D5: range compression (+2)
        rc=_f(r.get("range_contraction_pct")) or 0.0
        if rc>=30: score+=2
        elif rc>=15: score+=1
        # Demand dominant (+1)
        if _b(r.get("demand_dominant")): score+=1
        # Springboard (+1)
        if _b(r.get("w_springboard_present")): score+=1
        # Cause score (+1)
        c=_f(r.get("cause_score")) or 0.0
        if c>=75: score+=1
        # Accumulation (+2 — from Phase 9A finding)
        if str(r.get("behavior_classification","")).strip()=="ACCUMULATION": score+=2
        return score

    def dsb(score):
        if score>=8: return "D_8PLUS"
        if score>=6: return "D_6_7"
        if score>=4: return "D_4_5"
        if score>=2: return "D_2_3"
        return "D_0_1"

    # ── Study groups ──────────────────────────────────────────────────────────
    g_d1=defaultdict(list); g_d3=defaultdict(list); g_d5=defaultdict(list)
    g_dd=defaultdict(list); g_sp=defaultdict(list); g_ds=defaultdict(list)

    w_d1=defaultdict(list); w_d3=defaultdict(list); w_d5=defaultdict(list)
    w_dd=defaultdict(list); w_sp=defaultdict(list); w_ds=defaultdict(list)
    w_bhv=defaultdict(list)

    t_d1=defaultdict(list); t_d3=defaultdict(list); t_d5=defaultdict(list)
    t_dd=defaultdict(list); t_sp=defaultdict(list); t_ds=defaultdict(list)
    t_bhv=defaultdict(list); t_cs=defaultdict(list)

    # Cross combinations inside target bucket
    t_d1_bhv=defaultdict(list); t_d3_bhv=defaultdict(list)
    t_d5_bhv=defaultdict(list); t_ds_bhv=defaultdict(list)
    t_d1_d3=defaultdict(list); t_d1_d5=defaultdict(list)
    t_full_combo=defaultdict(list)

    for r,p,o,pr in enriched:
        spd=_b(r.get("w_selling_pressure_diminishing"))
        dei=_b(r.get("w_demand_efficiency_improving"))
        days=_f(r.get("p5_days_since_252_high")) or 0.0
        is_state1=spd and not dei
        is_winning=(ot(o)=="Q4" and pt(pr)=="Q4" and is_state1)
        is_target=is_winning and dur(days)=="DUR_60_120"

        d1b=d1(r); d3b=d3(r); d5b=d5(r)
        ddb=dd(r); spb=sp(r); csb=cs(r)
        bhvb=bhv(r)
        dsc=d_score(r); dsbb=dsb(dsc)

        g_d1[d1b].append(p); g_d3[d3b].append(p); g_d5[d5b].append(p)
        g_dd[ddb].append(p); g_sp[spb].append(p); g_ds[dsbb].append(p)

        if is_winning:
            w_d1[d1b].append(p); w_d3[d3b].append(p); w_d5[d5b].append(p)
            w_dd[ddb].append(p); w_sp[spb].append(p); w_ds[dsbb].append(p)
            w_bhv[bhvb].append(p)

        if is_target:
            t_d1[d1b].append(p); t_d3[d3b].append(p); t_d5[d5b].append(p)
            t_dd[ddb].append(p); t_sp[spb].append(p); t_ds[dsbb].append(p)
            t_bhv[bhvb].append(p); t_cs[csb].append(p)
            t_d1_bhv[d1b+"|"+bhvb].append(p)
            t_d3_bhv[d3b+"|"+bhvb].append(p)
            t_d5_bhv[d5b+"|"+bhvb].append(p)
            t_ds_bhv[dsbb+"|"+bhvb].append(p)
            t_d1_d3[d1b+"|"+d3b].append(p)
            t_d1_d5[d1b+"|"+d5b].append(p)
            t_full_combo[dsbb+"|"+bhvb+"|"+d1b].append(p)

    # ── Print results ─────────────────────────────────────────────────────────
    print("\n"+"="*100)
    print("Phase 9C: Behavioral Confirmation Layer (Track D)")
    print("  D1=FailureToFollowThrough  D3=VolumeAcceptance  D5=RangeCompression")
    print("="*100)

    print("\nSECTION 1: FULL UNIVERSE BASELINES")
    _pt("D1: Failure to Follow Through",g_d1)
    _pt("D3: Volume Acceptance (Vol Asymmetry)",g_d3)
    _pt("D5: Range Compression",g_d5)
    _pt("Demand Dominant",g_dd)
    _pt("Springboard Present",g_sp)
    _pt("D-Score Composite",g_ds)

    print("\nSECTION 2: WINNING COMBO (OBS_Q4+PROG_Q4+STATE_1)")
    _pt("D1 - Winning Combo",w_d1,min_n=3)
    _pt("D3 - Winning Combo",w_d3,min_n=3)
    _pt("D5 - Winning Combo",w_d5,min_n=3)
    _pt("Demand Dominant - Winning Combo",w_dd,min_n=3)
    _pt("Springboard - Winning Combo",w_sp,min_n=3)
    _pt("D-Score - Winning Combo",w_ds,min_n=3)
    _pt("Behavioral Class - Winning Combo",w_bhv,min_n=3)

    print("\nSECTION 3: TARGET BUCKET (OBS_Q4+PROG_Q4+STATE_1+DUR_60_120)")
    _pt("D1 - Target",t_d1,min_n=3)
    _pt("D3 - Target",t_d3,min_n=3)
    _pt("D5 - Target",t_d5,min_n=3)
    _pt("Demand Dominant - Target",t_dd,min_n=3)
    _pt("Springboard - Target",t_sp,min_n=3)
    _pt("Cause Score - Target",t_cs,min_n=3)
    _pt("Behavioral Class - Target",t_bhv,min_n=3)
    _pt("D-Score Composite - Target",t_ds,min_n=3)

    print("\nSECTION 4: CROSS-COMBINATIONS INSIDE TARGET BUCKET")
    _pt("D1 x Behavioral",t_d1_bhv,min_n=3)
    _pt("D3 x Behavioral",t_d3_bhv,min_n=3)
    _pt("D5 x Behavioral",t_d5_bhv,min_n=3)
    _pt("D1 x D3",t_d1_d3,min_n=3)
    _pt("D1 x D5",t_d1_d5,min_n=3)
    _pt("D-Score x Behavioral",t_ds_bhv,min_n=3)

    print("\nSECTION 5: FULL BEHAVIORAL CONFIRMATION COMBO")
    print("  D-Score tier x Behavioral Classification x D1")
    _pt("Full Combo",t_full_combo,min_n=3)

    print("\n"+"="*100)
    print("SPREAD SUMMARY — Phase 9C")
    print("="*100)
    pairs=[
        ("D1 Universe",g_d1,None),("D3 Universe",g_d3,None),
        ("D5 Universe",g_d5,None),("D-Score Universe",g_ds,None),
        ("D1 WinCombo",w_d1,None),("D3 WinCombo",w_d3,None),
        ("D-Score WinCombo",w_ds,None),
        ("D1 Target",None,t_d1),("D3 Target",None,t_d3),
        ("D5 Target",None,t_d5),("D-Score Target",None,t_ds),
        ("Behavioral Target",None,t_bhv),
        ("D-Score x Bhv",None,t_ds_bhv),
        ("Full Combo",None,t_full_combo),
    ]
    winners=[]
    for label,combo,tgt in pairs:
        cs_val=_sp(combo,min_n=3) if combo else None
        ts_val=_sp(tgt,min_n=3) if tgt else None
        best=cs_val or ts_val
        flag="PASS" if (best and best>=20) else ("NOTABLE" if (best and best>=10) else "")
        print("  %-30s  combo=%s  tgt=%s  %s" % (
            label,
            str(round(cs_val,1))+"pts" if cs_val else "N/A",
            str(round(ts_val,1))+"pts" if ts_val else "N/A",
            flag))
        if best and best>=10: winners.append((label,best))

    print("\n"+"="*100)
    print("PHASE 9C VERDICT")
    print("="*100)
    if winners:
        print("\n  Behavioral confirmation variables meeting threshold:")
        for label,sp in sorted(winners,key=lambda x:-x[1]):
            print("  %-30s  %.1fpts  %s" % (label,sp,"PASS" if sp>=20 else "NOTABLE"))
        print("\n  Top full behavioral confirmation triggers:")
        for s in _summ(t_full_combo,min_n=3)[:8]:
            print("  %-55s  n=%4d  mfe90=%7.2f%%  acc90=%5.1f%%" % (
                s["b"],s["n"],s["mfe90"],s["acc90"]))
    else:
        print("\n  No variable met threshold. Review Section 3 tables.")

if __name__=="__main__":
    csv_path=sys.argv[1] if len(sys.argv)>1 else "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
