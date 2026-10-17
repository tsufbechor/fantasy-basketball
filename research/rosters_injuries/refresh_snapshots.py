"""Refresh public ESPN 2026-27 team roster and injury-event snapshots.

Run from the repository root: python3 research/rosters_injuries/refresh_snapshots.py
Raw responses and per-response metadata are retained under raw/.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import csv, datetime, hashlib, json, re, requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; fantasy-basketball research)'}
SEASON = 2027

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json(), r.content

def save_raw(name, url, data, body, extra=None):
    name = f'{name}_{STAMP}'
    (RAW / f'{name}.json').write_bytes(body)
    meta = {'retrieved_at_utc': RETRIEVED, 'url': url, 'http_status': 200,
            'sha256': hashlib.sha256(body).hexdigest(), 'season_id': SEASON}
    if extra:
        meta.update(extra)
    (RAW / f'{name}.meta.json').write_text(json.dumps(meta, indent=2) + '\n')

RETRIEVED = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
teams_url = BASE + '/teams?limit=1000'
teams_doc, teams_body = fetch(teams_url)
teams = [x['team'] for x in teams_doc['sports'][0]['leagues'][0]['teams']]
if len(teams) != 30:
    raise RuntimeError(f'Expected 30 NBA teams, got {len(teams)}')
save_raw('espn_teams_2026-27', teams_url, teams_doc, teams_body, {'team_count': 30})

inj_url = BASE + '/injuries'
inj_doc, inj_body = fetch(inj_url)
save_raw('espn_injuries_2026-27', inj_url, inj_doc, inj_body,
         {'source_timestamp': inj_doc.get('timestamp'), 'season': inj_doc.get('season'),
          'injury_groups': len(inj_doc.get('injuries', []))})

def roster(t):
    ab = t['abbreviation']
    url = f'{BASE}/teams/{ab.lower()}/roster?season={SEASON}'
    doc, body = fetch(url)
    if doc.get('season', {}).get('year') != SEASON:
        raise RuntimeError(f'Wrong season returned for {ab}: {doc.get("season")}')
    return t, url, doc, body

roster_docs = {}
with ThreadPoolExecutor(max_workers=5) as pool:
    futures = [pool.submit(roster, t) for t in teams]
    for f in as_completed(futures):
        t, url, doc, body = f.result()
        ab = t['abbreviation']
        roster_docs[ab] = (t, url, doc)
        save_raw(f'espn_roster_{ab.lower()}_2026-27', url, doc, body,
                 {'source_timestamp': doc.get('timestamp'), 'team_id': t['id'],
                  'team_abbreviation': ab, 'player_count': len(doc.get('athletes', []))})

# Match Hashtag's ranked list by normalized name solely to surface roster players absent
# from the supplied ranking; the ESPN and Hashtag player IDs are different namespaces.
def norm(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())
hashtag_file = ROOT.parent.parent / 'hashtag_2026_27_no_to.html'
hashtag_names = set()
if hashtag_file.exists():
    html = hashtag_file.read_text(encoding='utf-8')
    hashtag_names = {norm(n) for n in re.findall(r'href="https://hashtagbasketball\.com/\d+/player"[^>]*>([^<]+)</a>', html)}

roster_rows = []
for ab, (team, url, doc) in sorted(roster_docs.items()):
    for a in doc.get('athletes', []):
        pos, status, exp = a.get('position') or {}, a.get('status') or {}, a.get('experience') or {}
        roster_rows.append({'team_abbreviation': ab, 'team_name': team['displayName'],
            'player_id': a.get('id'), 'player_name': a.get('fullName'),
            'position': pos.get('abbreviation'), 'jersey': a.get('jersey'),
            'roster_status': status.get('name'), 'roster_status_type': status.get('type'),
            'age': a.get('age'), 'experience_years': exp.get('years'), 'season_id': SEASON,
            'in_hashtag_ranked_file': bool(hashtag_names and norm(a.get('fullName')) in hashtag_names),
            'source': 'ESPN team roster API'})
with (ROOT / 'rosters_2026-27.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=roster_rows[0].keys()); w.writeheader(); w.writerows(roster_rows)

injury_rows = []
for group in inj_doc.get('injuries', []):
    for item in group.get('injuries', []):
        a = item.get('athlete') or {}; team = a.get('team') or {}; detail = item.get('details') or {}
        links = a.get('links') or []
        hrefs = ' '.join(l.get('href', '') for l in links)
        m = re.search(r'/id/(\d+)/', hrefs)
        fantasy = detail.get('fantasyStatus') or {}
        injury_rows.append({'team_abbreviation': team.get('abbreviation'),
            'team_name': team.get('displayName') or group.get('displayName'),
            'player_id': m.group(1) if m else '', 'player_name': a.get('displayName'),
            'status': item.get('status'), 'event_date_utc': item.get('date'),
            'injury_type': detail.get('type'), 'injury_location': detail.get('location'),
            'injury_detail': detail.get('detail'), 'return_date': detail.get('returnDate'),
            'fantasy_status': fantasy.get('abbreviation'), 'news_source': (item.get('source') or {}).get('description'),
            'season_id': SEASON, 'feed_source_timestamp': inj_doc.get('timestamp')})
fields = list(injury_rows[0].keys()) if injury_rows else ['team_abbreviation', 'player_name']
with (ROOT / 'injuries_2026-27.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(injury_rows)

# Latest ESPN item per team/player, with explicit age so consumers can reject stale events.
latest = {}
for row in injury_rows:
    key = (row['team_abbreviation'], norm(row['player_name']))
    if key not in latest or row['event_date_utc'] > latest[key]['event_date_utc']:
        latest[key] = row
with (ROOT / 'injuries_latest_event_2026-27.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(latest.values())
print(json.dumps({'retrieved_at_utc': RETRIEVED, 'teams': len(teams),
    'rosters_loaded': len(roster_docs), 'roster_players': len(roster_rows),
    'roster_players_not_in_hashtag_ranked_file': sum(x['in_hashtag_ranked_file'] is False for x in roster_rows),
    'injury_events': len(injury_rows), 'unique_latest_injury_events': len(latest),
    'injury_feed_source_timestamp': inj_doc.get('timestamp')}, indent=2))
