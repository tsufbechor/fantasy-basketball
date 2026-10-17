# NBA development and aging diagnostics

## Result

The repository already has full-league NBA regular-season player records from 1996–97 through 2025–26. These support useful descriptive age and adjacent-season diagnostics, but they do not identify true NBA experience year or provide historical preseason projections. I computed transitions from all players in those seasons, rather than only the players matched to Hashtag pages. The figures below are associations among players who appeared in both consecutive seasons; they are not causal estimates and should not be entered as fixed fantasy bonuses.

The archive contains 14,569 player-seasons and 11,272 adjacent-season player pairs. About 80.6% of player-seasons with an available following season have a player row in that next year. This makes a transition-on-returners curve a selected sample: exits and missed full NBA seasons must be modeled as a separate active/availability outcome, not treated as zero stat rates or silently dropped.

## What the adjacent-season data show

Each age band is the player's NBA-reported age in the first season of the pair. The table reports the median player-level change from that season to the next. Box-count rates are normalized per 100 team possessions using the player's team pace (NBA Stats defines pace as possessions per team per 48 minutes). FG% and FT% are median percentage-point changes. “Min/g” is median percent change in minutes per game. `N` counts consecutive-season pairs, not unique players.

| Start age | N | Min/g | PTS/100 | REB/100 | AST/100 | STL/100 | BLK/100 | 3PM/100 | FG% (pp) | FT% (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19–22 | 1,764 | +8.3% | +5.6% | +0.7% | +6.1% | +1.7% | −3.4% | +4.3% | +0.84 | +1.10 |
| 23–25 | 3,268 | +1.4% | +0.9% | −0.4% | +2.3% | −1.5% | −4.9% | +0.5% | −0.13 | +0.47 |
| 26–28 | 2,652 | −2.5% | −2.3% | −0.7% | −0.4% | −2.6% | −5.4% | −0.8% | −0.26 | +0.05 |
| 29–31 | 1,932 | −5.8% | −4.8% | −1.2% | −1.2% | −3.3% | −4.2% | −3.8% | −0.79 | −0.03 |
| 32–34 | 1,099 | −8.6% | −6.9% | −0.9% | −3.5% | −0.8% | −5.6% | −4.8% | −0.71 | −0.37 |
| 35+ | 554 | −13.2% | −8.3% | −2.6% | −4.4% | −3.6% | −3.5% | −8.0% | −1.15 | −0.76 |

The biggest early-career changes in this selected sample are in playing time, scoring rate, and assists. Later declines are not uniform across categories: blocks decline earlier, rebounds are comparatively flat, and steals have noisy age-band changes. The stable-looking percentages at some ages should not be mistaken for precise skill stability; shooting percentages have attempt-volume noise and change with role/shot mix.

Minutes and per-minute production are separable in these files. Across all paired seasons, mean minutes per game fell 0.38, while the median per-player change was −1.75%. For points, mean total season scoring fell by 19.9, of which the symmetric arithmetic decomposition attributes −19.0 to lower minutes and −0.8 to lower points per minute. For assists, the same decomposition is −5.6 assists from minutes and +2.0 from the per-minute rate, for a net −3.6. This illustrates why a single “aging percent” on total stats obscures the mechanism. The decomposition uses season totals and so is affected by schedule length and availability; the age table uses minutes per game and pace-normalized rates instead.

Usage is available as a partial offensive-role measure, but position is absent. Among returners age 29+, median PTS/100 changed −2.2% for players below 15% usage, −7.2% for 15–25% usage, and −5.7% for 25%+ usage (`N` 1,097 / 2,124 / 364). At ages 19–25 the corresponding median changes were +8.8%, +1.7%, and −1.4%. The nonmonotonic results and smaller high-usage cell reinforce that role should interact with age and be partially pooled; fixed role bands are only descriptive here. See `usage_role_age_metrics.csv` for other categories and minutes.

## Rookie and year-two/year-three transitions

The NBA stats rows do not include draft year, NBA debut year, or accumulated experience. “First season in this local panel” is not a valid rookie label: the panel starts in 1996–97, and a player can return after an absent NBA season. I therefore do not recommend treating the raw career-year 1→2 or 2→3 figures as rookie-development estimates.

For a limited proxy diagnostic, I took players first observed in the panel in 1998–99 or later, age 22 or younger, who also had a row the next season. There are 889 pairs. Median minute-per-game change was +15.8%, median PTS/min change +7.0%, AST/min +8.1%, FG% +1.13 percentage points, and FT% +1.63 points. Those are useful evidence that a young-player development signal exists, but the group includes possible veteran comebacks and misses first-year players who did not return; it is not a rookie coefficient. The script also computes an “observation year 2→3” panel proxy, but it is left-censored by the 1996 start and likewise must not be called NBA experience year 2→3.

To calculate the requested rookie→year 2 and year 2→year 3 curves, add a canonical NBA debut/first-season field for each NBA player ID (covering seasons before 1996), plus a distinct season-experience count. Preserve gaps so a full season without an NBA row can be marked as zero NBA participation. Then estimate both conditional production changes among returners and the probability of appearing in the next NBA season.

## Modeling recommendation

Use separate linked outcomes for (1) any NBA participation, (2) season availability such as games played, (3) minutes per game / role, and (4) category rates conditional on minutes. For counting categories, derive expected totals from expected minutes times expected rate; model FG% and FT% from makes and attempts rather than applying a percentage-point age bonus. Use per-100-possession or per-minute rates to reduce pace and minutes confounding, with season effects to account for changes in league environment.

Represent chronological age and NBA experience separately. Fit category-specific nonlinear age and experience functions, with age-by-role and experience-by-role effects where supported, and player-level random intercepts/slopes or another hierarchical shrinkage structure. Partial pooling should pull sparse late-career, rookie, and role cells toward the broader curve. Do not pool production counts and shooting percentages as if they had the same noise model. Use prior usage, starts, position/role when available, previous minutes, and prior rates as features. Missing whole NBA seasons are outcomes for participation, not evidence of zero skill.

Validate the increment with rolling season holdouts: train using only data available before each forecast season, tune only on earlier rolling folds, and compare against an unadjusted baseline. For actual Hashtag projections, calibrate forecast residuals only if dated pre-season projected stats can be recovered. The current ranking HTML snapshots are not historical forecasts, and their projections already encode human judgment, so fitting on them as if they were actuals would be invalid and could double-count the age signal.

## Computation and inputs

Run from the repository root or any directory:

```sh
python3 research/aging_development/cohort_diagnostics.py
```

The script reads the local `data/career/raw/league_dash_*_{base,advanced}.json` archive and writes all results into this directory. It merges multiple team stints per player-season, sums additive box statistics, reconstructs shooting percentages from total makes/attempts, and minutes-weights advanced fields. The archive and source collector are outside this research directory and were read only. Outputs are `cohort_summary.json`, `age_transition_metrics.csv`, and `usage_role_age_metrics.csv`.

Known limits: the source begins in 1996–97; NBA experience/debut is absent; team position is not in these endpoint rows; pace adjustment uses the player-team pace field as a proxy; scheduled games differ across strike-shortened, pandemic, and ordinary seasons; league rule/shot/role environments still change after pace adjustment; injury history and reason for nonparticipation are absent; the latest cohort has no future beyond 2025–26; and Hashtag historical preseason projections were not located. The descriptive transition estimates are also conditioned on consecutive NBA participation, which creates healthy-player and survivor selection at older ages.

## Sources

- Vaci, N., Cocić, D., Gula, B., & Bilalić, M. (2019). [Large data and Bayesian modeling—aging curves of NBA players](https://doi.org/10.3758/s13428-018-1183-8). *Behavior Research Methods*, 51, 1544–1564. This primary methodological study models development/aging jointly and shows how player position and minutes/activity can shape age trajectories.
- Lailvaux, S. P., Wilson, R. S., & Kasumovic, M. M. (2014). [Trait compensation and sex-specific aging of performance in male and female professional basketball players](https://doi.org/10.1111/evo.12375). *Evolution*, 68, 1523–1532. Their longitudinal NBA/WNBA analysis uses points per minute and mixed effects; it finds distinct trajectories by scoring type, supporting category-specific curves rather than a universal adjustment.
- NBA. [Stats glossary](https://www.nba.com/stats/help/glossary). Primary definition of possessions and other league measures. NBA.com describes pace as possessions per team per 48 minutes in its [2023–24 league scoring survey](https://www.nba.com/news/2023-24-nba-stats-survey-league-scoring-averages).
- Local input source: `data/career/raw/league_dash_*_base.json` and `_advanced.json`, collected using `nba_api.stats.endpoints.LeagueDashPlayerStats` in `scripts/collect_career_data.py`. The raw rows are NBA Stats regular-season outputs for all returned players, not just tracked Hashtag players.
