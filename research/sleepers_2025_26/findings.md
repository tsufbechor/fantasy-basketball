# Preseason fantasy basketball sleepers: 2025–26 archive

This archive preserves requested 2025–26 preseason advice as historical material. It is not a 2026–27 recommendation set. Searches and article review were performed on 2026-10-08; the NBA season has since completed, so every included recommendation is preseason hindsight from the point of view of the author at publication time.

## Coverage

The archive contains 14 article records and 72 player-mention records covering 35 distinct player names. It includes ESPN (two articles), RotoWire (three original features), NBA.com/RotoWire positional features (three), RotoBaller (two), Yahoo/For The Win, Yahoo High Score, DraftKings Network, and CBS Sports/SportsLine. Most items were read from the full article page or full search-indexed article; the ESPN roundtable and Yahoo/FTW were accessible through complete search-indexed text, while Yahoo's direct page returned a rate limit. The CBS item was published on opening night, so it is a near-draft-day snapshot.

Category leagues receive priority: NBA.com positional articles and several RotoWire/ESPN items explicitly discuss 9-category or 8-category value, stocks, roto, FG%, steals, blocks, and turnovers. General redraft articles are retained where they contain useful role, minutes, usage, development, or availability reasoning. The Yahoo High Score article is included for coverage but marked as a distinct one-best-game points format; its mentions should not be treated as category advice.

Sources and original publication/update dates are in [articles.json](articles.json). Player-level paraphrases, source author attribution, format, explicit rank/ADP where stated, risk, and player mapping are in [player_mentions.csv](player_mentions.csv). No article text is archived; summaries are concise paraphrases.

## Deduplication and use

NBA.com republishes RotoWire-authored center, guard, and forward sleeper features. Those pages remain separate article records with their displayed dates, but the three RotoWire positional pieces use one shared `source_family` in the metadata. Count a given Jonas Nader/player recommendation once when estimating author-level coverage. Other repeated player names across publications are separate author claims only where the recommendation was actually made separately; syndicated copies and repeated publication of the same article are not independent votes.

Across the table, there are 71 distinct player-by-credited-author pairs (after splitting shared bylines). Matas Buzelis has 7 credited authors; Jaden Ivey and Kevin Porter Jr. have 5 each; Cam Whitmore has 4. These counts retain publication-level author attributions and collapse only same-author player repetitions from the syndicated RotoWire positional family. The files preserve per-article mentions rather than assign a consensus score. Mention frequency is a descriptive coverage measure only: it reflects who published an article, article scope and format, and search coverage, not probability of success or validated predictive value. Player lists have different definitions of “sleeper,” different draft markets and different timing.

## Data quality and limitations

- The Hashtag mapping file at `data/career/player_mapping.csv` matched 68 of 72 mentions (94%). Four `Cam Whitmore` mentions are preserved as `unmatched_preserved`; no Hashtag/player ID mapping was present in that local table. `Alex Sarr` was normalized to mapped `Alexandre Sarr`, and common Kel’el Ware / T.J. McConnell spellings were normalized explicitly.
- The archive is intentionally broad but not exhaustive. Search indexing differs across publishers, pages can be updated or removed, and paywalls or rate limits restrict direct access. The ESPN sleeper roundtable was reviewed via its full indexed text; the Yahoo/FTW direct URL was rate-limited but its full article body appeared in search results. The guard feature's NBA.com page shows an October 13 update but does not expose an original publication date, so the original date is unknown and only `updated` is recorded.
- `published` dates are the visible original date when available. An update is separately stored in `updated`; missing dates are `null`, never inferred from crawl age. The NBA.com article pages' publication/update stamps are as shown by those pages.
- ADP/rank values are recorded only when the article explicitly supplied them, without trying to harmonize Yahoo, Fantrax, aggregate ADP, or ranking systems.
- Some broader article labels include “breakout” as well as “sleeper”; the author’s original classification is retained in `classification` rather than silently reinterpreted.
- Current-season results were not used to alter the preseason claims. No hindsight or in-season recommendation is mixed into the mention table.

## Source list

- ESPN, Sep 18, 2025: [Sleepers, breakouts and busts for 2025–26](https://www.espn.com/fantasy/basketball/story/_/id/46293178/fantasy-basketball-sleepers-breakouts-busts-nba-2025-26), five experts.
- ESPN / Jim McCormick, Sep 29, 2025: [Matas Buzelis, Tari Eason and other top sleepers](https://www.espn.com/fantasy/basketball/story/_/id/46421889/fantasy-basketball-top-sleepers-target-nba-2025-26).
- RotoWire / Alex Barutha, Sep 11, 2025: [Sleepers & breakouts: Best upside picks](https://www.rotowire.com/basketball/article/fantasy-basketball-breakout-sleepers-2025-2026-96016).
- RotoWire / Mike Barner, Sep 24, 2025: [Best NBA value picks](https://www.rotowire.com/basketball/article/five-fantasy-basketball-sleepers-to-watch-this-nba-season-96453).
- RotoWire / Alex Barutha and Nick Whalen, Sep 29, 2025: [Underrated and undervalued sleepers](https://www.rotowire.com/basketball/article/fantasy-basketball-sleepers-2025-26-96622).
- NBA.com / Jonas Nader, Sep 5, 2025: [Forward sleepers](https://www.nba.com/news/nba-fantasy-6-sleeper-picks-forwards-in-2025-26).
- NBA.com / Jonas Nader, Sep 10, 2025: [Center sleepers](https://www.nba.com/news/nba-fantasy-6-center-sleeper-picks-for-2025-26).
- NBA.com / Jonas Nader, original date not displayed; updated Oct 13, 2025: [Guard sleepers](https://www.nba.com/news/nba-fantasy-6-sleeper-picks-guards-in-2025-26).
- RotoBaller / Aidin Ebrahimi, Sep 27, 2025: [Guard sleepers](https://www.rotoballer.com/fantasy-basketball-sleepers-guards-values-for-2025-2026/1707888).
- RotoBaller / Andrew Ball, Sep 30, 2025: [Forward sleepers](https://www.rotoballer.com/fantasy-basketball-sleepers-forwards-2025/1703322).
- For The Win / Charles Curtis, syndicated at Yahoo, Oct 14, 2025: [Seven draft sleepers](https://sports.yahoo.com/article/7-fantasy-basketball-sleepers-2025-192750896.html).
- DraftKings Network / Bill Yin, Oct 9, 2025: [Sleepers and breakouts](https://dknetwork.draftkings.com/2025/10/09/top-fantasy-basketball-sleepers-and-breakouts-for-2025-26/).
- Yahoo / Dan Titus, Oct 2, 2025: [High Score guard sleepers](https://sports.yahoo.com/fantasy/article/fantasy-basketball-high-score-sleepers-late-round-guards-to-target-for-yahoos-new-hoops-format-175332466.html), separate scoring format.
- CBS Sports / Ross Kelly and SportsLine model, Oct 21, 2025: [Model sleepers, breakouts and busts](https://www.cbssports.com/fantasy/basketball/news/fantasy-basketball-rankings-2025-nba-breakouts-busts-sleepers-picks-adp/).
