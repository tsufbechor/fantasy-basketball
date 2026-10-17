#!/usr/bin/env python3
"""Resumable Hashtag-to-NBA career season collector. See data/career/README.md."""
from __future__ import annotations
import csv, json, re, sys, time, unicodedata
from datetime import date
from collections import defaultdict
from pathlib import Path
from typing import Any
import pandas as pd
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, playercareerstats

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/career'; RAW=OUT/'raw'
SNAPSHOTS=['Fantasy Basketball Rankings 2022-25 _ Hashtag Basketball.html','Fantasy Basketball Rankings 2025-26 _ Hashtag Basketball.html','hashtag_2026_27_no_to.html']
START=1996; _today=date.today(); END=_today.year-1 if _today.month>=7 else _today.year-2 # latest completed NBA regular season
DELAY=1.5; RETRIES=3

def norm(s):
 s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().casefold()
 return re.sub(r'[^a-z0-9]','',s)
def season_label(y): return f'{y}-{str(y+1)[-2:]}'
def read_players():
 players={}
 for filename in SNAPSHOTS:
  p=ROOT/filename
  if not p.exists(): raise FileNotFoundError(p)
  soup=BeautifulSoup(p.read_text(errors='replace'),'html.parser')
  links=soup.select('a[id*="GridView1_HyperLink1_"]')
  if not links: links=[a for a in soup.select('a[href*="/player"]') if a.get_text(' ',strip=True)]
  names={}
  for a in links:
   name=a.get_text(' ',strip=True); m=re.search(r'/([0-9]+)/player',a.get('href',''))
   if name and m: names[name]=m.group(1)
  print(f'{filename}: {len(names)} unique full names')
  for n,hid in names.items(): players.setdefault(hid,{'hashtag_id':hid,'hashtag_name':n,'snapshots':set()})['snapshots'].add(filename)
 return players

def fetch(season,measure):
 path=RAW/f'league_dash_{season}_{measure.lower()}.json'
 if path.exists():
  doc=json.loads(path.read_text()); return pd.DataFrame(doc['data'],columns=doc['columns'])
 last=None
 for attempt in range(RETRIES):
  try:
   f=leaguedashplayerstats.LeagueDashPlayerStats(season=season,season_type_all_star='Regular Season',measure_type_detailed_defense=measure,timeout=45).get_data_frames()[0]
   doc={'source':'nba_api.stats.endpoints.LeagueDashPlayerStats','season':season,'measure_type':measure,'columns':list(f.columns),'data':f.astype(object).where(pd.notnull(f),None).values.tolist()}
   path.write_text(json.dumps(doc,separators=(',',':'),ensure_ascii=False)); time.sleep(DELAY); return f
  except Exception as e:
   last=e; print(f'failed {season} {measure} try {attempt+1}: {e}',file=sys.stderr); time.sleep(3*(attempt+1))
 raise RuntimeError(f'{season} {measure}: {last}')

def fetch_career(player_id):
 path=RAW/f'player_career_{player_id}.json'
 if path.exists(): return json.loads(path.read_text())
 last=None
 for attempt in range(RETRIES):
  try:
   f=playercareerstats.PlayerCareerStats(player_id=player_id,per_mode36='Totals',timeout=45).get_data_frames()[0]
   doc={'source':'nba_api.stats.endpoints.PlayerCareerStats','player_id':player_id,'columns':list(f.columns),'data':f.astype(object).where(pd.notnull(f),None).values.tolist()}
   path.write_text(json.dumps(doc,separators=(',',':'),ensure_ascii=False));time.sleep(DELAY);return doc
  except Exception as e:
   last=e;print(f'failed career teams {player_id} try {attempt+1}: {e}',file=sys.stderr);time.sleep(3*(attempt+1))
 raise RuntimeError(f'player {player_id}: {last}')

def main():
 OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
 players=read_players();
 # Honor explicitly reviewed mappings between runs.
 mapfile=OUT/'player_mapping.csv'; manual={}
 if mapfile.exists():
  for r in csv.DictReader(mapfile.open()):
   if r.get('nba_player_id','').isdigit() and r.get('mapping_status')=='manual': manual[r['hashtag_id']]=int(r['nba_player_id'])
 season_rows=[]; source_names=defaultdict(set); source_id_name={}
 errors=[]
 for y in range(START,END+1):
  seas=season_label(y)
  try:
   base=fetch(seas,'Base'); adv=fetch(seas,'Advanced')
   for r in base.itertuples(index=False):
    pid=int(r.PLAYER_ID); name=str(r.PLAYER_NAME); source_names[norm(name)].add(pid); source_id_name[pid]=name
   adidx=defaultdict(list)
   for r in adv.to_dict('records'): adidx[int(r['PLAYER_ID'])].append(r)
   for pid, group in list(adidx.items()):
    total_rows=[x for x in group if str(x.get('TEAM_ABBREVIATION'))=='TOT']
    if total_rows: adidx[pid]=total_rows
   baseidx=defaultdict(list)
   for r in base.to_dict('records'): baseidx[int(r['PLAYER_ID'])].append(r)
   target_names={norm(x['hashtag_name']) for x in players.values()}
   for pid, group in baseidx.items():
    total_rows=[x for x in group if str(x.get('TEAM_ABBREVIATION'))=='TOT']
    if total_rows: group=total_rows
    name=group[0]['PLAYER_NAME']
    if norm(str(name)) not in target_names and pid not in manual.values(): continue
    total={}
    additive=('GP','GS','MIN','FGM','FGA','FG3M','FTM','FTA','OREB','DREB','REB','AST','STL','BLK','PTS','TOV','PF')
    for col in additive:
     if col in group[0]: total[col]=sum(float(x.get(col) or 0) for x in group)
    total.update({'PLAYER_ID':pid,'PLAYER_NAME':name,'AGE':group[0].get('AGE'),'TEAM_ABBREVIATION':'/'.join(sorted({str(x['TEAM_ABBREVIATION']) for x in group})),'TEAM_COUNT':max(int(x.get('TEAM_COUNT') or 1) for x in group)})
    total['FG_PCT']=total['FGM']/total['FGA'] if total.get('FGA') else None
    total['FT_PCT']=total['FTM']/total['FTA'] if total.get('FTA') else None
    ag=adidx.get(pid,[]); mins=sum(float(x.get('MIN') or 0) for x in ag)
    if ag:
     for col in ag[0]:
      if col in ('USG_PCT','PACE','PIE','AST_PCT','REB_PCT','NET_RATING','OFF_RATING','DEF_RATING'):
       total[col]=sum(float(x.get(col) or 0)*float(x.get('MIN') or 0) for x in ag)/mins if mins else None
    total['SEASON']=seas; season_rows.append(total)
  except Exception as e: errors.append({'season':seas,'error':str(e)}); print('Season incomplete:',seas,e,file=sys.stderr)
  if y%10==0: print(f'processed through {seas}; seasons={y-START+1}')

 # Deterministic normalized full-name matching only. Ambiguity stays unresolved.
 mapping=[]; hashtag_to_nba={}
 for hid,p in players.items():
  n=p['hashtag_name']; ids=source_names.get(norm(n),set()); status='unmatched'; nba_id=''; nba_name=''
  if hid in manual: nba_id=manual[hid]; nba_name=source_id_name.get(nba_id,''); status='manual'
  elif len(ids)==1: nba_id=next(iter(ids)); nba_name=source_id_name[nba_id]; status='exact_normalized_name'
  elif len(ids)>1: status='ambiguous_source_name'
  if nba_id!='': hashtag_to_nba[hid]=int(nba_id)
  mapping.append({'hashtag_id':hid,'hashtag_name':n,'nba_player_id':nba_id,'nba_full_name':nba_name,'mapping_status':status,'snapshots':'|'.join(sorted(p['snapshots']))})
 with mapfile.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(mapping[0])); w.writeheader(); w.writerows(mapping)
 # Enrich team names for tracked multi-team seasons from per-player career records.
 mapped_ids=set(hashtag_to_nba.values()); team_errors=[]; team_lookup={}; career_totals={}; career_seasons=defaultdict(set)
 for pid in sorted(mapped_ids):
  pid_seasons={str(r['SEASON']) for r in season_rows if int(r['PLAYER_ID'])==pid}
  years=sorted(int(x[:4]) for x in pid_seasons)
  has_internal_gap=bool(years and len(set(years)) != years[-1]-years[0]+1)
  has_multiple_teams=any(int(r['PLAYER_ID'])==pid and int(r.get('TEAM_COUNT') or 1)>1 for r in season_rows)
  if not (has_internal_gap or has_multiple_teams): continue
  try:
   doc=fetch_career(pid); ix={c:i for i,c in enumerate(doc['columns'])}; per_season=defaultdict(set); gs_by_season=defaultdict(list)
   for vals in doc['data']:
    season=str(vals[ix['SEASON_ID']]); team=str(vals[ix['TEAM_ABBREVIATION']])
    career_seasons[pid].add(season)
    gs_by_season[season].append((team,vals[ix['GS']]))
    if team!='TOT': per_season[season].add(team)
   for season,records in gs_by_season.items():
    totals=[gs for team,gs in records if team=='TOT']
    career_totals[(pid,season)]={'GS':totals[0] if totals else sum(gs for team,gs in records if team!='TOT')}
   for season,teams in per_season.items():
    if len(teams)>1: team_lookup[(pid,season)]='/'.join(sorted(teams))
  except Exception as e: team_errors.append({'player_id':pid,'error':str(e)})
 # canonical mapped NBA id-season rows, include optional returned fields
 bykey={}
 for r in season_rows:
  pid=int(r['PLAYER_ID'])
  if pid not in mapped_ids: continue
  if (pid,r['SEASON']) in team_lookup: r['TEAM_ABBREVIATION']=team_lookup[(pid,r['SEASON'])]
  if (pid,r['SEASON']) in career_totals: r.update(career_totals[(pid,r['SEASON'])])
  bykey[(pid,r['SEASON'])]=r
 fields=['PLAYER_ID','PLAYER_NAME','SEASON','TEAM_ABBREVIATION','GP','GS','AGE','MIN','FGM','FGA','FG_PCT','FTM','FTA','FT_PCT','FG3M','PTS','REB','AST','STL','BLK','USG_PCT']
 out=[]
 for (pid,seas),r in sorted(bykey.items(),key=lambda x:(x[0][0],int(x[0][1][:4]))):
  row={'player_id':pid,'player_name':r.get('PLAYER_NAME'),'season':seas,'team_or_teams':r.get('TEAM_ABBREVIATION')}
  for src,dst in [('GP','games_played'),('GS','games_started'),('AGE','age'),('MIN','minutes_total'),('FGM','fgm_total'),('FGA','fga_total'),('FG_PCT','fg_pct'),('FTM','ftm_total'),('FTA','fta_total'),('FT_PCT','ft_pct'),('FG3M','fg3m_total'),('PTS','points_total'),('REB','rebounds_total'),('AST','assists_total'),('STL','steals_total'),('BLK','blocks_total'),('USG_PCT','usage_pct')]: row[dst]=r.get(src)
  if row.get('usage_pct') is not None:
   row['usage_pct']=row['usage_pct']*100 if row['usage_pct']<=1 else row['usage_pct']
  gp=row['games_played'];
  for total,pg in [('minutes_total','minutes_per_game'),('fga_total','fga_per_game'),('fta_total','fta_per_game')]: row[pg]=(row[total]/gp if gp else None) if row[total] is not None else None
  out.append(row)
 with (OUT/'player_seasons.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]) if out else ['player_id','player_name','season']);w.writeheader();w.writerows(out)
 # coverage based on each mapped player's source career records found across queried seasons.
 rowsby=defaultdict(list)
 for row in out: rowsby[row['player_id']].append(row)
 cov=[]
 for m in mapping:
  pid=m['nba_player_id']; hist=rowsby.get(int(pid),[]) if pid else []
  seasons=sorted((r['season'] for r in hist),key=lambda s:int(s[:4])); have={int(s[:4]) for s in seasons}
  career_years={int(s[:4]) for s in career_seasons.get(int(pid),set()) if START<=int(s[:4])<=END} if pid else set()
  if career_years:
   lo,hi=min(career_years),max(career_years); expected=career_years
  elif seasons:
   lo,hi=int(seasons[0][:4]),int(seasons[-1][:4]); expected=set(range(lo,hi+1))
  else: lo=hi=0; expected=set()
  gaps=sorted(expected-have); no_record=sorted(set(range(lo,hi+1))-career_years) if career_years else []
  status=('unmapped' if not pid else 'mapped_no_source_rows') if not pid or not seasons else ('season_wide_gap_despite_career_record' if gaps else ('no_career_record_in_interval' if no_record else ('complete_player_career_endpoint_span' if career_years else 'complete_between_observed_seasons')))
  cov.append({'hashtag_id':m['hashtag_id'],'hashtag_name':m['hashtag_name'],'nba_player_id':pid,'mapping_status':m['mapping_status'],'career_first_season':season_label(lo) if lo else '', 'career_last_season':season_label(hi) if hi else '', 'expected_seasons_in_range':len(expected),'retrieved_seasons':len(have & expected),'missing_seasons':'|'.join(season_label(y) for y in gaps),'seasons_without_career_record':'|'.join(season_label(y) for y in no_record),'career_endpoint_seasons':len(career_years),'failed_retrieval_seasons':'|'.join(e['season'] for e in errors),'coverage_status':status})
 with (OUT/'coverage_report.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(cov[0]));w.writeheader();w.writerows(cov)
 (OUT/'collection_errors.json').write_text(json.dumps(errors,indent=2))
 (OUT/'team_enrichment_errors.json').write_text(json.dumps(team_errors,indent=2))
 print(f'tracked={len(players)} mapped={len(hashtag_to_nba)} rows={len(out)} errors={len(errors)}')
 if out:
  print('season range',min(r['season'] for r in out),max(r['season'] for r in out))
 print('unmapped',sum(not m['nba_player_id'] for m in mapping),'missing usage',sum(r['usage_pct'] is None for r in out))
if __name__=='__main__': main()
