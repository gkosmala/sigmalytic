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
    return {"mfe90":mfe90,"mfe20":mfe20,"acc90":acc90,"asym":asym,
        "h1r":_f(r.get("h1_return_pct")) or 0.0,
        "h1m":_f(r.get("h1_mfe_pct")) or 0.0,
        "h1d":_f(r.get("h1_direction_correct")) or 0.0,
        "h3r":_f(r.get("h3_return_pct")) or 0.0,
        "h3m":_f(r.get("h3_mfe_pct")) or 0.0,
        "h3d":_f(r.get("h3_direction_correct")) or 0.0,
        "h5r":_f(r.get("h5_return_pct")) or 0.0,
        "h5m":_f(r.get("h5_mfe_pct")) or 0.0,
        "h5d":_f(r.get("h5_direction_correct")) or 0.0,
        "h10m":_f(r.get("h10_mfe_pct")) or 0.0,
        "h20m":_f(r.get("h20_mfe_pct")) or 0.0}

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
    def h1b(v):
        if v>=3: return "H1_3PCT+"
        if v>=1: return "H1_1_3PCT"
        if v>=0: return "H1_FLAT"
        return "H1_DOWN"
    def h3b(v):
        if v>=5: return "H3_5PCT+"
        if v>=2: return "H3_2_5PCT"
        if v>=0: return "H3_FLAT"
        return "H3_DOWN"
    def h5b(v):
        if v>=7: return "H5_7PCT+"
        if v>=3: return "H5_3_7PCT"
        if v>=0: return "H5_FLAT"
        return "H5_DOWN"

    g_h1=defaultdict(list); g_h3=defaultdict(list); g_h5=defaultdict(list)
    w_h1=defaultdict(list); w_h3=defaultdict(list); w_h5=defaultdict(list)
    t_h1=defaultdict(list); t_h3=defaultdict(list); t_h5=defaultdict(list)
    t_bhv=defaultdict(list); t_h1_bhv=defaultdict(list)
    t_h3_bhv=defaultdict(list); t_combo=defaultdict(list)

    for r,p,o,pr in enriched:
        spd=_b(r.get("w_selling_pressure_diminishing"))
        dei=_b(r.get("w_demand_efficiency_improving"))
        days=_f(r.get("p5_days_since_252_high")) or 0.0
        is_state1=spd and not dei
        is_winning=(ot(o)=="Q4" and pt(pr)=="Q4" and is_state1)
        is_target=is_winning and dur(days)=="DUR_60_120"
        bhv=str(r.get("behavior_classification","")).strip() or "UNK"
        h1=p["h1r"]; h3=p["h3r"]; h5=p["h5r"]
        h1bk=h1b(h1); h3bk=h3b(h3); h5bk=h5b(h5)

        g_h1[h1bk].append(p)
        g_h3[h3bk].append(p)
        g_h5[h5bk].append(p)
        if is_winning:
            w_h1[h1bk].append(p)
            w_h3[h3bk].append(p)
            w_h5[h5bk].append(p)
        if is_target:
            t_h1[h1bk].append(p)
            t_h3[h3bk].append(p)
            t_h5[h5bk].append(p)
            t_bhv[bhv].append(p)
            t_h1_bhv[h1bk+"|"+bhv].append(p)
            t_h3_bhv[h3bk+"|"+bhv].append(p)
            t_combo[h1bk+"|"+h3bk+"|"+bhv].append(p)

    print("\n"+"="*100)
    print("Phase 9B: 1-5 Day Follow-Through Confirmation")
    print("="*100)

    print("\nSECTION 1: FULL UNIVERSE")
    _pt("H1 Return Bucket",g_h1)
    _pt("H3 Return Bucket",g_h3)
    _pt("H5 Return Bucket",g_h5)

    print("\nSECTION 2: WINNING COMBO (OBS_Q4+PROG_Q4+STATE_1)")
    _pt("H1 Return - Winning Combo",w_h1,min_n=3)
    _pt("H3 Return - Winning Combo",w_h3,min_n=3)
    _pt("H5 Return - Winning Combo",w_h5,min_n=3)

    print("\nSECTION 3: TARGET BUCKET (DUR_60_120)")
    _pt("H1 Return - Target",t_h1,min_n=3)
    _pt("H3 Return - Target",t_h3,min_n=3)
    _pt("H5 Return - Target",t_h5,min_n=3)
    _pt("Behavioral Class - Target",t_bhv,min_n=3)

    print("\nSECTION 4: H1 x BEHAVIORAL CLASS")
    _pt("H1 x Behavioral",t_h1_bhv,min_n=3)

    print("\nSECTION 5: H3 x BEHAVIORAL CLASS")
    _pt("H3 x Behavioral",t_h3_bhv,min_n=3)

    print("\nSECTION 6: COMBO (H1 x H3 x BEHAVIORAL)")
    _pt("Full Combo",t_combo,min_n=3)

    print("\nSPREAD SUMMARY")
    for label,data in [("H1 Universe",g_h1),("H3 Universe",g_h3),
            ("H1 WinCombo",w_h1),("H3 WinCombo",w_h3),
            ("H1 Target",t_h1),("H3 Target",t_h3),
            ("H5 Target",t_h5),("Behavioral Target",t_bhv)]:
        sp=_sp(data,min_n=3)
        flag="PASS" if (sp and sp>=15) else ("NOTABLE" if (sp and sp>=10) else "")
        print("  %-25s  %s  %s" % (label,str(round(sp,1))+"pts" if sp else "N/A",flag))

    print("\nTOP ENTRY TRIGGERS (H1 x H3 x Behavioral)")
    for s in _summ(t_combo,min_n=3)[:8]:
        print("  %-55s  n=%4d  mfe90=%7.2f%%  acc90=%5.1f%%" % (s["b"],s["n"],s["mfe90"],s["acc90"]))

if __name__=="__main__":
    csv_path=sys.argv[1] if len(sys.argv)>1 else "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
