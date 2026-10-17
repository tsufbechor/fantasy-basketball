# Scoring from the consolidated fantasy dataset

Date: 2026-10-08 (Asia/Jerusalem). Status: transparent baseline and measured
availability experiment; a final injury-aware draft ranking has not been calibrated.

## Objective and current evidence

Use Hashtag's eight-category player projections as the initial forecasting opinion.
Retain its published rank, TOTAL, projected GP and selected 20% GP penalty as source
fields. Calculate our own inspectable category value separately. An undocumented
ranking penalty is not a learned availability forecast, and the original TOTAL is
not directly comparable to a new z-score sum.

Career collection passes its source validator: 366 tracked Hashtag IDs, 356 mapped
NBA IDs and 2,209 player-seasons. The 10 unresolved names remain in the universe.
The full-league cache adds 30 seasons for cohort training. Source records are not
limited to today's surviving players, but adjacent-season production analyses are
still conditional on continued participation.

Roster snapshots cover 30 teams and 606 preseason roster entries. Membership is
not projected playing time. NBA and ESPN IDs are different namespaces, and name
matching needs explicit ambiguity/conflict reporting. Current injury truth has
not been established by the event-oriented ESPN news feed.

The 2025-26 sleeper archive contains 14 source records, 72 mentions and 35 names.
It is historical evidence for testing forecast theses, not upcoming-season advice.
Article mirrors and same-author repetition must not become independent votes.

## 1. Forecast the basketball variables before ranking

Keep three related quantities separate:

1. Participation and availability: probability of NBA participation, games played,
   and the timing/clustering of missed games.
2. Opportunity: minutes, possessions and role conditional on playing, including
   current teammates, rotations and return-from-injury scenarios.
3. Skill/production: category rates conditional on minutes and role, with age,
   experience, shot mix and player history as features.

For scenario s, counting output is GP_s * MPG_s * rate_per_minute_s. Expected
output is the probability-weighted sum over scenarios, not necessarily the product
of three independent means. Health and workload, for example, are related.
Shooting percentages are derived from expected makes and attempts, not multiplied
by GP, minutes or usage. Usage is a scoring-opportunity predictor, not an all-stat
multiplier. Project assists and defensive categories separately.

Hashtag already embeds role, availability and development judgments. A new model
should compare its estimates with those assumptions. Do not add an age bonus,
injury penalty and teammate bonus on top of the same already-adjusted forecast.

## 2. A transparent per-game eight-category baseline

For each of the six counting categories (PTS, REB, AST, STL, BLK, 3PM), calculate
z_i,c = (x_i,c - mean_ref,c) / sd_ref,c.

Calculate shooting impact from volume:

- FG impact_i = FGM_i - p_ref_FG * FGA_i.
- FT impact_i = FTM_i - p_ref_FT * FTA_i.
- p_ref_FG = sum_ref(FGM) / sum_ref(FGA), and similarly for FT.

Standardize each impact across the same reference player pool. This is an
attempt-weighted approximation to roster percentage contribution, not an exact
team-specific percentage marginal. With an actual roster, recompute the change
in total makes divided by total attempts.

Sum the eight z-scores with equal weights for an initial neutral eight-category
index. This creates a transparent comparison metric; it does not prove equal
z-score weights maximize H2H standings or reproduce Hashtag's H2H category floor.
Keep the reference pool, means and standard deviations fixed when comparing
players/scenarios. Filtering the UI or removing drafted players must not silently
redefine the baseline. Test reference-pool sensitivity before relying on fine rank
differences. Hashtag's rounded display statistics constrain numerical precision.

## 3. Durability belongs in usable production and replacement value

Do NOT multiply a signed total z-score by GP/82. A negative sum can become less
negative when a player misses games, falsely rewarding lower availability.
Likewise do not apply another GP penalty to Hashtag's original penalized TOTAL.

For availability sensitivity, calculate scenario raw counting production and
shooting makes/attempts first, then compare those values using a fixed reference
and an explicit fantasy replacement baseline. Missed NBA games do not imply an
equal number of usable replacement games. Schedule collisions, starting slots,
bench depth, IR eligibility and league acquisition rules constrain replacement.

The league snapshot has H2H_CATEGORY scoring, 12 teams, 12 active slots and 6
bench slots plus 2 IR. Verify the scoring subtype/tiebreak behavior and decode the
acquisition-limit fields before simulating standings or streaming. Raw API fields
must not be interpreted as an intuitively named weekly limit without validation.

An initial roster-neutral index is useful for comparing players; a draft-aware
score eventually estimates the marginal change in expected category results when
adding a player and replacing a realistic alternative. It should consider all
eight categories and the league's actual standings objective. Punting is a user
strategy, not an automatic consequence of one weak category.

## 4. A measured availability experiment

`scripts/test_availability_model.py` reads full-league cached Base records. It
fits a standardized ridge regression using the previous three availability
rates, prior age and age squared, prior MPG, and availability variability.
Regularization is selected using chronological validation seasons 2015-16
through 2018-19. Held-out tests refit only on seasons preceding each target
season: 2023-24, 2024-25 and 2025-26.

To avoid the original diagnostic's uniform 75-game assumption for unequal
2019-20 schedules, this experiment excludes any four-season window touching
2019-20. Uniform 50-, 66- and 72-game schedules are normalized. Predictions are
bounded to 0-100% availability; errors are expressed as 82-game equivalents.

Across the same 908 held-out player-seasons:

| Model | MAE (games) | RMSE (games) | Mean overprediction (games) |
|---|---:|---:|---:|
| Prior-season availability | 16.63 | 22.13 | 4.30 |
| Prior-three-season mean | 16.27 | 21.39 | 4.82 |
| Ridge with age/workload/history | 14.87 | 19.10 | 2.45 |

The model improves MAE by about 8.6% versus the three-year mean on this selected
sample. The improvement occurs in each of the three test seasons. This is
promising predictive evidence, not a calibrated injury-risk model or an established
optimal blend with Hashtag. The sample requires participation in the target season
and three preceding seasons, so excludes full missed seasons, exits and rookies.
No current injuries, injury diagnoses, rest or roster-change features are included.
Prediction intervals have not been calibrated. Preserve these limits whenever
using the result. Coefficients are predictive associations, not causal weights.

`availability_projection_comparison.csv` applies the experimental model alongside
Hashtag for 227 of the 300 projected players with all three required history
seasons. The other 73 remain explicitly unmodeled. It uses an all-observed-data fit
for upcoming 2026-27, while the reported holdout errors above come from strictly
earlier training folds. These independent diagnostics do not change fantasy scores.

| Player | Hashtag GP | Experimental conditional GP |
|---|---:|---:|
| Nikola Jokic | 72 | 64.4 |
| Joel Embiid | 52 | 43.4 |
| Anthony Davis | 59 | 48.0 |

These differences identify assumptions to investigate with current health,
rest and role evidence. They do not establish that Hashtag is wrong. The model
has no current injury features and is conditional on participating in the NBA.

## 5. Development and role weights must earn inclusion

Age diagnostics show different patterns by category and playing time. They do
not justify copying cohort median changes into each player's projection. Estimate
true NBA experience separately from age and calendar years since first observation.
NBA debut years and fully missed seasons need validation before labeling year-1-to-2
and year-2-to-3 effects.

A first chronological probe (`scripts/test_development_model.py`) compares ridge
models using three lagged category rates and prior MPG, with and without age and
age squared. Each model's regularization is selected on 2015-16 through 2018-19;
2023-24 through 2025-26 are held out with preceding seasons only for training.
Like the availability test, it excludes windows touching 2019-20 and requires
three preceding consecutive seasons plus target-season participation. Production
rates are per minute, not pace-adjusted, and minutes are a separate target.

| Target | MAE without age | MAE with age | Incremental MAE improvement |
|---|---:|---:|---:|
| MPG | 3.79594 | 3.73397 | 1.63% |
| PTS/min | 0.06463 | 0.06428 | 0.54% |
| REB/min | 0.02445 | 0.02445 | -0.03% |
| AST/min | 0.02045 | 0.02003 | 2.03% |
| STL/min | 0.00831 | 0.00829 | 0.34% |
| BLK/min | 0.00623 | 0.00623 | 0.10% |
| 3PM/min | 0.01230 | 0.01229 | 0.11% |
| FGA/min | 0.04507 | 0.04465 | 0.93% |
| FTA/min | 0.02361 | 0.02370 | -0.38% |

Age adds little in this model family after accounting for history. The result
supports testing category-specific effects, not a blanket youth bonus. It does
not test rookies, true experience, causal aging, teammate opportunity, current
injuries or whether age corrects Hashtag residuals. No uncertainty intervals or
multiple-model-selection adjustment were computed; small differences are
exploratory and should not be treated as statistically established improvements.

Test age/experience models against lagged per-minute or per-possession baselines,
using chronological folds and season effects. Fit shooting makes/attempts with
appropriate exposure rather than noisy raw percentage changes. Partially pool
sparse cohorts and shrink small teammate splits. Proposed constants such as a
120-minute split shrinkage prior are hypotheses, not validated model weights.

For each category, a candidate blend is:
projection = Hashtag_projection + lambda_c * (independent_projection - Hashtag_projection).

Learn lambda_c against genuinely dated preseason forecast residuals. It can differ
for MPG, GP, shooting and counting categories. Only one selected historical Top-30
Hashtag snapshot is currently validated, so there is insufficient evidence to fit
a general residual correction. Until validated, the operative adjustment is zero;
show independent scenarios alongside Hashtag instead of silently replacing it.

## 6. News and expert opinions are forecast evidence

News entries should identify player, source, event time, retrieval time, status,
corrections and freshness. A dated coach-confirmed restriction can change a minutes
scenario. An old 'Out' event does not establish current absence. Absence from an
injury feed does not establish health. Roster updates and injury returns must update
both player availability and teammate opportunity, without duplicating the effect.

The RotoWire RSS proof currently retains five event records; reruns and a simulated
correction were tested. These are rule-classified paraphrases, not verified current
injury diagnoses. The five-item feed is a narrow observation window, not a complete
league injury inventory. ESPN's 101 injury-event rows include old events and are
likewise not current status. Keep these linked as evidence, excluded from numerical
scores until freshness, context and claim accuracy are validated.

Sleeper coverage can be tested as a historical feature: did an explicit minutes
or role thesis anticipate the eventual change beyond existing preseason forecasts?
Mention counts are not extra fantasy points. Keep categories, points-only advice,
publication timing, author and syndicated source families distinguishable.

## Deliverable sequence

First: a validated joined player table, inspectable eight-category baseline and
projection-versus-history differences. Next: fresh injury truth, true experience,
usable teammate splits and age/role holdout tests. Finally: tested projection
corrections and league-specific replacement/matchup scoring. Do not label the
baseline as the final draft recommendation engine.

## Reproduce and inspect

From the project root, run `./.venv/bin/python scripts/consolidate_scoring.py`,
then `./.venv/bin/python scripts/test_availability_model.py` and
`./.venv/bin/python scripts/test_development_model.py`. The career validator is
`./.venv/bin/python scripts/validate_career_data.py`. Source snapshots are read-only.

The baseline and source diagnostics are in `data/consolidated/`; model experiments
are in `research/scoring/`. Full career histories remain in
`data/career/player_seasons.csv` joined through the NBA ID in `tracked_players.csv`.
The current projection table carries the last-three-season trends, while the
two-season actuals table includes explicit source-presence flags. No missing
history or unmatched identity is silently treated as zero production.
