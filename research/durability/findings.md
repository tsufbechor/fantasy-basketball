# NBA availability / Hashtag GP durability research

## Scope and evidence collected

The target is a 12-team ESPN head-to-head category league with FG%, FT%, 3PM, PTS, REB, AST, STL, and BLK; turnovers are excluded. The saved 2026–27 Hashtag page is configured for H2H averages and a 20% GP penalty. Hashtag defines its H2H ranking mode as a -2 floor for a negative category value, while its `Based On` control switches between per-game averages and totals. Its user guide describes the available controls, but does not explain a statistical derivation for the selectable GP penalty. [Hashtag user guide](https://hashtagbasketball.com/user-guide)

The local historical source is the NBA Stats `LeagueDashPlayerStats` Base cache under `data/career/raw/`, which currently covers 1996–97 through 2025–26 (30 seasons, 14,569 player-seasons). The diagnostics script reads only those raw caches and writes files in this directory. It combines player/team stints by summing GP, normalizes GP by the team schedule maximum, and caps the normalized outcome at 1.0. Schedule denominators are 82 except 1998–99 (50), 2011–12 (66), 2019–20 (75), and 2020–21 (72). Official NBA sources confirm the 2011–12 and 2020–21 short schedules and that Dallas had 75 games in the 2019–20 restart schedule. [2011–12 schedule](https://pr.nba.com/nba-2011-12-game-broadcast-schedules/), [2020–21 schedule](https://official.nba.com/nba-announces-structure-and-format-for-2020-21-season/), [2019–20 restart schedule](https://www.nba.com/nba-returns-2020-faq)

### Historical one-season-ahead diagnostics

For players with a GP record in the target season and three consecutive preceding seasons, I compared three simple, transparent forecasts on the *same* 7,276 player-season sample. Forecasts use only information from before the target season. Errors are expressed as equivalent GP in an 82-game season.

| Forecast | MAE | RMSE | Bias (forecast − actual) |
|---|---:|---:|---:|
| Prior-season league availability mean | 19.5 GP | 22.5 GP | −6.0 GP |
| Player’s prior-season availability rate | 16.4 GP | 22.7 GP | +4.3 GP |
| Simple mean of prior 3 availability rates | 15.6 GP | 21.2 GP | +5.2 GP |

The 3-year mean has the lowest error among these deliberately simple baselines, but it still overpredicts on average. This is a rolling descriptive backtest, not a fitted model or a claim that a fixed 3-year mean is optimal. It excludes rookies and players without three continuous seasons, and it does not include explicit injuries, roster role, minutes, or workload.

Conditional next-season availability varies substantially with recent GP and age in that survivor cohort. For example, players whose prior-season availability was at least 80% had mean next-season availability of 78.6% (n=4,112; median 86.6%; 10th–90th percentile 46.3%–98.8%). Those below 20% prior availability averaged 43.7% (n=267; median 38.9%; p10–p90 4.9%–90.7%). By target-season age, mean availability was 73.4% ages 25–29 (n=3,431), 69.4% ages 30–34 (n=2,415), and 64.7% ages 35–39 (n=683). The wide within-group percentiles show why a point estimate alone hides useful risk. These are conditional summaries, not age coefficients; they include only players who continued to appear and had three prior seasons.

The paper *It’s a Hard-Knock Life* likewise reports that age and experience findings are mixed, while NBA career length and workload were associated with injury risk in its 2012–15 sample. A 2021 NBA injury-forecasting study found that prior injury, game activity, and player statistics interact, and emphasized class imbalance and noisy public injury records. These papers support testing several signals and evaluating calibration; neither supplies defensible coefficients for a fantasy GP forecast. [Hard-Knock Life paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC6107769/), [METIC injury-forecasting paper](https://journals.sagepub.com/doi/10.3233/JSA-200529)

### Dated Hashtag projection archive and validation feasibility

The Internet Archive CDX index for Hashtag’s projection page surfaced captures that help establish feasibility, but not a long preseason history:

- [13 Aug 2024 capture](https://web.archive.org/web/20240813054959/https://hashtagbasketball.com/fantasy-basketball-projections) still serves the 2023–24 rest-of-season page.
- [30 Jul 2025 capture](https://web.archive.org/web/20250730192747/https://hashtagbasketball.com/fantasy-basketball-projections) still serves the 2024–25 rest-of-season page.
- [9 Oct 2025 capture](https://web.archive.org/web/20251009174024/https://hashtagbasketball.com/fantasy-basketball-projections) serves 2025–26 projections and has 30 player rows. It is genuinely preseason: the 2025–26 NBA regular season began Oct. 21. Its saved settings are Top 30, ESPN position source, H2H, averages, and 20% GP penalty. [NBA schedule release](https://www.nba.com/news/2025-26-nba-regular-season-schedule)
- [28 Aug 2026 capture](https://web.archive.org/web/20260828001207/https://hashtagbasketball.com/fantasy-basketball-projections) and [27 Sep 2026 capture](https://web.archive.org/web/20260927201109/https://hashtagbasketball.com/fantasy-basketball-projections) preserve 2026–27 pages, each with only 30 rows.

I extracted the 30 archived 2025–26 GP forecasts and matched every name by exact normalized full name to the NBA Stats 2025–26 actuals. On that small Top 30 sample, Hashtag GP had MAE 14.5 and mean bias +8.4 GP; a constant 65.6 GP (20% below 82) had MAE 12.5 and bias +5.1 GP; the same players’ 2024–25 GP had MAE 17.8 and bias +4.7 GP. This is one selected top-30 sample from one season, so it cannot establish that the fixed value generalizes or support estimating a better replacement penalty. It does establish that an archived projection can be paired with actuals for at least one historical season. The archive page’s `Yahoo` ADP source is irrelevant to the GP field, though the saved 2026–27 page uses ESPN.

The current Hashtag projection’s GP field is a season availability forecast, while a GP penalty changes the ranking formula. Those should be evaluated separately: first test projected GP against actual GP; then test whether converting forecast uncertainty and missed-game production to fantasy value improves draft decisions.

## Proposed model and fantasy-value treatment

Use team games available as the exposure denominator, so a 50-, 66-, 72-, or disrupted 75-game schedule does not masquerade as a player durability change. For player (i), define historical availability (A_{i,t}=\min(GP_{i,t},S_t)/S_t). Forecast an availability distribution, not only a mean:

\[
GP_{i,t+1}=S_{t+1} A_{i,t+1},\qquad
A_{i,t+1}\mid X_{i,t}\sim F(\text{recent availability, age, NBA experience, minutes/workload, injury history, current report}).
\]

Start with a regularized model for mean availability using lagged seasons, nonlinear age and NBA-experience terms, current minutes/role, and injury status. Estimate recency weights and effects only in chronological training folds; reserve later seasons for evaluation. For uncertainty, use calibrated predictive quantiles or a bootstrap over held-out residuals conditional on risk strata. Report mean GP and 10th/50th/90th percentile GP, plus probabilities of being below practical thresholds such as 50 and 65 games. Evaluate MAE/RMSE, bias, quantile coverage, calibration by age / injury / prior-GP bands, and high-risk recall. Never treat a missing season as zero unless the source distinguishes retirement, non-NBA employment, and a fully missed injury season.

An injury feature needs dated injury events or historical NBA injury reports; annual GP alone cannot tell whether a player missed games for one long injury, several short injuries, healthy rest, role loss, or retirement. Current official NBA reports include injury, illness, other medical conditions, and rest with participation status, but they are day-of information and should update the season forecast as scenarios rather than be inferred from last year’s GP. [NBA injury-report rules](https://official.nba.com/nba-injury-report-2025-26-season/)

For fantasy decisions, estimate the **marginal production over the actual replacement path**, not a uniform percentage haircut. The local ESPN league export confirms 12 teams and contains lineup-slot, acquisition-limit, and roster settings; the slot-ID mapping and effective IR capacity need to be confirmed before computing replacement value. Estimate replacement from the available ESPN waiver pool after accounting for roster size, starting slots, and IR capacity. For a player expected to miss games, compare the player’s per-game category contribution with the likely bench/waiver replacement for those scheduled team games, capped by weekly lineup limits and NBA schedule overlap. For FG% and FT%, simulate attempts and makes (team percentages are volume-weighted); avoid treating a percentage point as a simple count stat. Since this is weekly H2H, the best final test is a matchup simulation using the roster and ESPN weekly schedule: draw player availability and category production, fill lineup slots with bench/streamers, and compare category-win probabilities. A healthy player’s additional games add value only when they displace less production or fill otherwise empty lineup capacity.

## Gaps and next steps

- The raw NBA GP history is broad enough for league-wide preliminary analyses, but it is not a complete player-specific feature table yet. The career mapping/season outputs were absent at the time of this run; diagnostics therefore use the full NBA player pool, not only the current Hashtag universe.
- Injury events/status, daily game logs, team role/minutes forecasts, and current 2026–27 NBA schedules are absent from the durability inputs. These are needed before fitting the requested injury-aware uncertainty model.
- Only one usable archived preseason page found so far contains enough rows for an actual-versus-forecast check (Top 30, 2025–26). The 2024 capture is stale; the 2026 captures cannot yet be checked against completed outcomes. Search Wayback CDX again for older captures or other dated projection pages before considering the archive history adequate for model calibration.
- The 30-player test suggests Hashtag’s current GP forecasts and a uniform 20% adjustment should be judged independently. A single season and selected Top 30 is too small to choose a revised coefficient.

## Reproduction

From the project root, with the project virtual environment:

```sh
./.venv/bin/python research/durability/analyze_gp.py
./.venv/bin/python research/durability/validate_hashtag_gp.py
```

`analyze_gp.py` reads the raw cached LeagueDash Base JSON and creates `season_coverage.csv`, `backtest_summary.csv`, and `conditional_summary.csv`. `validate_hashtag_gp.py` retrieves the archived Oct. 9, 2025 Hashtag page, parses its Top 30 GP column, exact-normalized-name matches it to the 2025–26 and 2024–25 NBA Stats caches, then writes `hashtag_2025_26_preseason_gp_validation.csv`. The scripts never modify source caches.
