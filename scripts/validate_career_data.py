#!/usr/bin/env python3
"""Validate generated career outputs against cached NBA Stats source responses."""
import csv, json, math, unicodedata
from pathlib import Path
from collections import Counter, defaultdict
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/career'; RAW=OUT/'raw'

def norm(s): return ''.join(c.lower() for c in unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode() if c.isalnum())
def read_csv(path):
 with path.open(newline='') as f: return list(csv.DictReader(f))
def load(season,measure): return json.loads((RAW/f'league_dash_{season}_{measure}.json').read_text())
def main():
 mapping=read_csv(OUT/'player_mapping.csv'); rows=read_csv(OUT/'player_seasons.csv'); coverage=read_csv(OUT/'coverage_report.csv')
 assert len({m['hashtag_id'] for m in mapping})==len(mapping), 'duplicate Hashtag ID'
 assert len({(r['player_id'],r['season']) for r in rows})==len(rows), 'duplicate player-season key'
 assert len(coverage)==len(mapping), 'coverage report misses tracked players'
 required=['player_id','player_name','season','team_or_teams','games_played','minutes_total','minutes_per_game','fga_total','fga_per_game','fta_total','fta_per_game','usage_pct']
 for field in required: assert all(r[field] for r in rows), f'missing required field: {field}'
 for r in rows:
  gp=float(r['games_played']); assert 0<gp<=100, f'implausible GP: {r}'
  assert 0<=float(r['minutes_total'])<=7000, f'implausible minutes: {r}'
  assert 0<=float(r['usage_pct'])<=100, f'usage outside 0-100: {r}'
  for total,per_game in [('minutes_total','minutes_per_game'),('fga_total','fga_per_game'),('fta_total','fta_per_game')]:
   assert math.isclose(float(r[total]),float(r[per_game])*gp,rel_tol=1e-9,abs_tol=1e-8), f'{per_game} does not reconcile: {r}'
 # Exact normalized name mappings must point to an ID that supplied that name.
 source=defaultdict(set)
 for p in RAW.glob('league_dash_*_base.json'):
  doc=json.loads(p.read_text()); ix={name:i for i,name in enumerate(doc['columns'])}
  for v in doc['data']: source[norm(v[ix['PLAYER_NAME']])].add(int(v[ix['PLAYER_ID']]))
 for m in mapping:
  if m['mapping_status']=='exact_normalized_name':
   key=norm(m['hashtag_name'])
   assert int(m['nba_player_id']) in source[key], f"invalid exact mapping: {m['hashtag_name']}"
 # Compare full-season totals with raw source records for long-career, traded and rookie examples.
 rows_by={(int(r['player_id']),r['season']):r for r in rows}
 cases=[(2544,'2003-04','LeBron James'),(2544,'2025-26','LeBron James'),(202710,'2024-25','Jimmy Butler III'),(1641717,'2025-26','Cooper Flagg')]
 checks=[]
 for pid,season,name in cases:
  actual=rows_by[(pid,season)]; base=load(season,'base'); ix={c:i for i,c in enumerate(base['columns'])}
  src=next(v for v in base['data'] if int(v[ix['PLAYER_ID']])==pid)
  for out,raw in [('games_played','GP'),('minutes_total','MIN'),('fga_total','FGA'),('fta_total','FTA')]:
   assert math.isclose(float(actual[out]),float(src[ix[raw]]),rel_tol=1e-9,abs_tol=1e-8), f'{name} {season}: {out} differs from LeagueDash'
  checks.append(f'{name} {season}')
 # Traded-team example must agree with per-player regular-season stints and total row.
 career=json.loads((RAW/'player_career_202710.json').read_text()); ci={c:i for i,c in enumerate(career['columns'])}
 jimmy=[v for v in career['data'] if v[ci['SEASON_ID']]=='2024-25']
 teams=sorted({v[ci['TEAM_ABBREVIATION']] for v in jimmy if v[ci['TEAM_ABBREVIATION']]!='TOT'})
 total=next(v for v in jimmy if v[ci['TEAM_ABBREVIATION']]=='TOT'); jr=rows_by[(202710,'2024-25')]
 assert jr['team_or_teams']=='/'.join(teams), 'traded teams do not match PlayerCareerStats'
 for out,raw in [('games_played','GP'),('minutes_total','MIN'),('fga_total','FGA'),('fta_total','FTA')]:
  assert (abs(float(jr[out])-float(total[ci[raw]]))<0.5 if raw=='MIN' else math.isclose(float(jr[out]),float(total[ci[raw]]),rel_tol=1e-9,abs_tol=1e-8)), f'Jimmy Butler 2024-25 {out} differs from career totals'
 assert not json.loads((OUT/'collection_errors.json').read_text()), 'season collection errors exist'
 assert not json.loads((OUT/'team_enrichment_errors.json').read_text()), 'team enrichment errors exist'
 print(f'PASS: {len(mapping)} tracked players; {len(rows)} unique player-seasons; {len(checks)} source spot-checks plus traded-stint validation.')
 print('Optional blank fields:', {f:sum(not r.get(f,'') for r in rows) for f in ('games_started','fg_pct','ft_pct')})
 print('Coverage:',Counter(r['coverage_status'] for r in coverage))
 print('Spot-checks:', '; '.join(checks), '; Jimmy Butler 2024-25 teams/totals')
if __name__=='__main__': main()
