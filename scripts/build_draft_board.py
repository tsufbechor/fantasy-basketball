"""Package the saved Hashtag top 300 as an extension and a standalone HTML file."""
import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'

class HashtagGrades(HTMLParser):
    """Read category grades from the saved rankings table, keyed by Hashtag ID."""
    def __init__(self, path):
        super().__init__()
        self.inside = False
        self.cells = []
        self.player_id = None
        self.grades = {}
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and attrs.get('id') == 'ContentPlaceHolder1_GridView1':
            self.inside = True
        if not self.inside:
            return
        if tag == 'tr':
            self.cells, self.player_id = [], None
        if tag == 'td':
            self.cells.append(attrs.get('class', ''))
        if tag == 'a' and 'GridView1_HyperLink1_' in attrs.get('id', ''):
            match = re.search(r'/(\d+)/player', attrs.get('href', ''))
            if match:
                self.player_id = match[1]

    def handle_endtag(self, tag):
        if self.inside and tag == 'tr' and self.player_id and self.player_id not in self.grades:
            # The eight selected categories precede TOTAL; only projections include ADP.
            self.grades[self.player_id] = self.cells[-9:-1]
        if tag == 'table':
            self.inside = False

categories = ['fg_pct', 'ft_pct', 'three_pm', 'points', 'rebounds', 'assists', 'steals', 'blocks']
projection_grades = HashtagGrades(ROOT / 'hashtag_2026_27_no_to.html').grades
actual_grades = HashtagGrades(ROOT / 'Fantasy Basketball Rankings 2025-26 _ Hashtag Basketball.html').grades
with (ROOT / 'data/consolidated/hashtag_actuals.csv').open() as handle:
    actuals = {r['hashtag_id']: r for r in csv.DictReader(handle) if r['season'] == '2025-26' and r['html_snapshot_included'] == 'True'}

def stats(row, fields, grades):
    result = {key: float(row[field]) if row[field] else None for key, field in fields.items()}
    result['grades'] = dict(zip(categories, grades))
    return result

projection_fields = {key: key for key in categories + ['fgm_pg_display', 'fga_pg_display', 'ftm_pg_display', 'fta_pg_display']}
actual_fields = {key: 'historical_hashtag_' + {'three_pm': '3pm', 'points': 'pts', 'rebounds': 'reb', 'assists': 'ast', 'steals': 'stl', 'blocks': 'blk'}.get(key, key) for key in projection_fields}
with (ROOT / 'data/consolidated/hashtag_projections_2026_27.csv').open() as handle:
    rows = sorted(csv.DictReader(handle), key=lambda row: int(row['rank']))[:300]
players = []
for row in rows:
    if not row['espn_player_id']:
        raise ValueError(f"Missing ESPN ID: {row['hashtag_name']}")
    players.append({'id':row['espn_player_id'], 'name':row['hashtag_name'],
                    'team':row['hashtag_team'], 'position':row['position'],
                    'sourceRank':int(row['rank']),
                    'projected': stats(row, projection_fields, projection_grades[row['hashtag_id']]),
                    'actual': stats(actuals[row['hashtag_id']], actual_fields, actual_grades[row['hashtag_id']]) if row['hashtag_id'] in actuals else None})
assert len(players) == 300 and len({p['id'] for p in players}) == 300
data = json.dumps(players, ensure_ascii=False, indent=2)
(EXT / 'players.json').write_text(data + '\n')
html = (EXT / 'panel.html').read_text()
html = html.replace('<link rel="stylesheet" href="panel.css">', '<style>' + (EXT / 'panel.css').read_text() + '</style>')
core = (EXT / 'draft.mjs').read_text().replace('export function ', 'function ')
app = (EXT / 'panel.mjs').read_text().split('\n', 1)[1]
app = app.replace("const players = await (await fetch('./players.json')).json();", 'const players = ' + data + ';')
script = '(async () => {\n' + core + app + '\n})().catch(error => { document.body.append(document.createTextNode("Board could not load: " + error.message)); });'
html = html.replace('<script type="module" src="panel.mjs"></script>', '<script>' + script.replace('</script', '<\\/script') + '</script>')
(ROOT / 'my-draft-board.html').write_text(html)
print(f'Built {len(players)} players → my-draft-board.html and extension/players.json')
