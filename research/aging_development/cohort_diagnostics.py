#!/usr/bin/env python3
"""Reproducible descriptive NBA cohort transitions from local LeagueDash JSON.

Reads data/career/raw/league_dash_*_{base,advanced}.json; writes only beside this file.
The inputs are full-league season rows (not the tracked-player union). No forecasts or
weights are fit here. Run from any directory with Python 3: python3 cohort_diagnostics.py
"""
from __future__ import annotations
import csv, json, math, re, statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1] / "data" / "career" / "raw"

def load_season(season: str):
    base_doc=json.loads((RAW/f"league_dash_{season}_base.json").read_text())
    adv_doc=json.loads((RAW/f"league_dash_{season}_advanced.json").read_text())
    base=[dict(zip(base_doc['columns'],r)) for r in base_doc['data']]
    adv=[dict(zip(adv_doc['columns'],r)) for r in adv_doc['data']]
    # NBA API may return one row per team for traded players; sum additive box stats,
    # then form attempts-weighted percentages and minutes-weighted advanced rates.
    by={}
    additive=['GP','GS','MIN','FGM','FGA','FG3M','FG3A','FTM','FTA','OREB','DREB','REB','AST','TOV','STL','BLK','PTS']
    for r in base:
        p=int(r['PLAYER_ID']); q=by.setdefault(p,{'id':p,'name':r['PLAYER_NAME'],'age':float(r['AGE']),'teams':set(),**{x:0.0 for x in additive}})
        q['teams'].add(str(r.get('TEAM_ABBREVIATION','')))
        for k in additive: q[k]+=float(r.get(k) or 0)
    adv_by=defaultdict(list)
    for r in adv: adv_by[int(r['PLAYER_ID'])].append(r)
    for p,q in by.items():
        q['fg_pct']=q['FGM']/q['FGA'] if q['FGA'] else None
        q['ft_pct']=q['FTM']/q['FTA'] if q['FTA'] else None
        ar=adv_by.get(p,[]); den=sum(float(x.get('MIN') or 0) for x in ar)
        for key in ('USG_PCT','PACE','TS_PCT','AST_PCT','REB_PCT'):
            q[key.lower()]=(sum(float(x.get(key) or 0)*float(x.get('MIN') or 0) for x in ar)/den if den else None)
        q['season']=season
    return by

files=sorted(RAW.glob('league_dash_*_base.json'))
seasons=[]
for f in files:
    season=re.search(r'league_dash_(\d{4}-\d{2})_base',f.name).group(1)
    if (RAW/f'league_dash_{season}_advanced.json').exists(): seasons.append(season)
panel={s:load_season(s) for s in seasons}
years={s:int(s[:4]) for s in seasons}

def next_season(s):
    y=years[s]+1
    return f'{y}-{str(y+1)[-2:]}'

def ratio(q, key):
    mins=q['MIN']
    return q[key]/mins if mins else None

COUNT=['PTS','REB','AST','STL','BLK','FG3M','TOV','FGA','FTA']
METRICS=['minutes_total','minutes_per_game','games_played']+[k.lower()+'_per_min' for k in COUNT]+[k.lower()+'_per_100_team_possessions' for k in COUNT]+['fg_pct','ft_pct','usage_pct','pace']
def vec(q):
    x={'minutes_total':q['MIN'],'minutes_per_game':q['MIN']/q['GP'] if q['GP'] else None,'games_played':q['GP']}
    for k in COUNT:
        x[k.lower()+'_per_min']=ratio(q,k)
        # Pace is possessions per team per 48 minutes; per-minute rates become
        # per-100 team possessions with this player-team pace proxy.
        x[k.lower()+'_per_100_team_possessions']=(ratio(q,k)*4800/q['pace'] if q['pace'] else None)
    x['fg_pct']=q['fg_pct']; x['ft_pct']=q['ft_pct']; x['usage_pct']=q['usg_pct']; x['pace']=q['pace']
    return x

def describe(transitions, key):
    before=[]; after=[]; delta=[]; pct=[]
    for a,b in transitions:
        x=vec(a).get(key); y=vec(b).get(key)
        if x is None or y is None or not math.isfinite(float(x)) or not math.isfinite(float(y)): continue
        x=float(x); y=float(y); before.append(x); after.append(y); delta.append(y-x)
        if x!=0: pct.append((y-x)/abs(x)*100)
    if not delta:return {'n':0}
    return {'n':len(delta),'mean_start':statistics.mean(before),'mean_end':statistics.mean(after),'mean_delta':statistics.mean(delta),'median_delta':statistics.median(delta),'median_pct_change':statistics.median(pct) if pct else None}

alltrans=[]; ret=[]; new=[]
for s in seasons:
    ns=next_season(s)
    if ns not in panel: continue
    cur,nxt=panel[s],panel[ns]
    ret.extend((s,p) for p in cur if p in nxt)
    alltrans.extend((cur[p],nxt[p]) for p in cur.keys() & nxt.keys())
    new.extend((ns,p) for p in nxt if p not in cur)

# Age is measured at start of season. Bins deliberately broad enough for readable
# descriptive cells; this remains an observed-stayer estimand.
age_bins=[('19-22',19,22),('23-25',23,25),('26-28',26,28),('29-31',29,31),('32-34',32,34),('35+',35,100)]
age_rows=[]
for label,lo,hi in age_bins:
    tr=[(a,b) for a,b in alltrans if lo<=a['age']<=hi]
    for m in METRICS:
        d=describe(tr,m)
        if d.get('n'): age_rows.append({'age_at_start':label,'metric':m,**d})

# Usage is a partial proxy for offensive role (not position or defensive role).
# Report age/role cells to expose heterogeneity; thresholds are readable bands, not
# recommended production cutoffs.
role_rows=[]
for label,lo,hi in [('usage<15%',-1,0.15),('usage15-25%',0.15,0.25),('usage>=25%',0.25,2)]:
    for agelabel,alo,ahi in [('19-25',19,25),('26-28',26,28),('29+',29,100)]:
        tr=[(a,b) for a,b in alltrans if a['usg_pct'] is not None and lo<=a['usg_pct']<hi and alo<=a['age']<=ahi]
        for metric in ('minutes_per_game','pts_per_100_team_possessions','reb_per_100_team_possessions','ast_per_100_team_possessions','stl_per_100_team_possessions','blk_per_100_team_possessions','fg3m_per_100_team_possessions','fg_pct','ft_pct'):
            d=describe(tr,metric)
            if d.get('n'): role_rows.append({'age_at_start':agelabel,'baseline_usage_band':label,'metric':metric,**d})

# First-seen-in-panel season is not necessarily NBA rookie year: panel starts in
# 1996-97 and veteran comeback seasons are possible. This is explicitly a proxy.
first={}
for s in seasons:
    for p,q in panel[s].items(): first.setdefault(p,(s,q))
first_eligible=[]
for p,(s,q) in first.items():
    if years[s] < 1998 or q['age']>22: continue
    ns=next_season(s)
    if ns in panel and p in panel[ns]: first_eligible.append((q,panel[ns][p]))

# Proxy observation year 2->3: players seen in two consecutive panel seasons, then
# next consecutive season. Not true NBA experience for left-censored panel players.
second_to_third=[]
for s in seasons:
    s2=next_season(s); s3=f'{years[s]+2}-{str(years[s]+3)[-2:]}'
    if s2 not in panel or s3 not in panel: continue
    for p,q in panel[s2].items():
        if p in panel[s] and p in panel[s3]: second_to_third.append((q,panel[s3][p]))

summary={'source':'Local NBA Stats LeagueDashPlayerStats base+advanced JSON; regular season',
 'seasons':seasons,'season_count':len(seasons),'all_player_season_rows':sum(map(len,panel.values())),
 'adjacent_transition_count':len(alltrans),'all_player_return_pairs':len(ret),
 'rookie_to_year2_proxy_n':len(first_eligible),'observation_year2_to_3_proxy_n':len(second_to_third),
 'older_age_definition':'age in first season of adjacent pair; observed in both consecutive seasons',
 'selection_note':'Age and development transitions condition on appearing in both consecutive NBA seasons. Players with no next-season row contribute to retention counts, not stat deltas.',
 'metrics':{m:describe(alltrans,m) for m in METRICS},
 'rookie_to_year2_proxy':{m:describe(first_eligible,m) for m in METRICS},
 'observation_year2_to_3_proxy':{m:describe(second_to_third,m) for m in METRICS},
 'return_rate':len(ret)/sum(len(panel[s]) for s in seasons[:-1] if next_season(s) in panel) if any(next_season(s) in panel for s in seasons[:-1]) else None}

# Add symmetric exact decomposition of seasonal-count stat changes into total
# minutes and per-minute rate for each tracked box-count metric. Counts = minutes*rate.
decomp={}
for k in COUNT:
    bits=[]; raw_d=[]
    for a,b in alltrans:
        ma,mb=a['MIN'],b['MIN']; ra=ratio(a,k); rb=ratio(b,k)
        if ra is None or rb is None: continue
        dm=(mb-ma)*(ra+rb)/2; dr=(rb-ra)*(ma+mb)/2
        bits.append((dm,dr)); raw_d.append(b[k]-a[k])
    decomp[k.lower()]={'n':len(bits),'mean_total_change':statistics.mean(raw_d) if raw_d else None,
      'mean_change_attributed_to_minutes':statistics.mean(x for x,y in bits) if bits else None,
      'mean_change_attributed_to_per_minute_rate':statistics.mean(y for x,y in bits) if bits else None,
      'identity_max_abs_error':max((abs((x+y)-z) for (x,y),z in zip(bits,raw_d)),default=None)}
summary['count_change_decomposition']=decomp

(HERE/'cohort_summary.json').write_text(json.dumps(summary,indent=2))
with (HERE/'age_transition_metrics.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['age_at_start','metric','n','mean_start','mean_end','mean_delta','median_delta','median_pct_change']);w.writeheader();w.writerows(age_rows)
with (HERE/'usage_role_age_metrics.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['age_at_start','baseline_usage_band','metric','n','mean_start','mean_end','mean_delta','median_delta','median_pct_change']);w.writeheader();w.writerows(role_rows)
print(json.dumps(summary,indent=2))
