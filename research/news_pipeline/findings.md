# NBA player-news ingestion feasibility

## Result

A manual, repeatable ingestion proof works against RotoWire's publisher-provided NBA RSS feed: `https://www.rotowire.com/rss/news.php?sport=NBA`. The feed is public XML and responded with HTTP 200. In the tested fetch at **2026-10-07 22:12:55 UTC** (2026-10-08 01:12:55 Asia/Jerusalem), it contained **5 items**; the newest item was published **2026-10-07 18:58:00 UTC**. The HTTP `Last-Modified` header was 22:10:25 UTC and `Cache-Control` was `public, max-age=300`. The feed's official page says it provides sport-specific player-news/article XML feeds, including NBA, for RSS readers and blogs/personal websites: [RotoWire RSS feeds](https://www.rotowire.com/rss/).

The first run stored five unique feed events; an immediate second run stored zero new events, found zero revisions, and counted all five as unchanged. All five names matched the local 2026-27 roster CSV (ESPN IDs); unmatched names are retained with `player_match.status = unmatched`. A separate correction simulation changed only an RSS description: the script recorded one revision against the same event ID, kept the total at five, and did not persist the description. Records carry a UTC publication timestamp, original publisher timezone/date text, fetch time, source/profile URL, RotoWire item ID, publisher player profile ID, local roster match, short rule-based paraphrase, category tags, and an explicit `historical_news_event` / `current_status: not_inferred` distinction.

The persisted store contains no article description or full article text. The source description is read in memory only to compute a digest, so an edited report can be detected without retaining the prose. The paraphrases are simple keyword-based and intentionally conservative; they are not an AI interpretation of the article.

## NBC Sports / Rotoworld check

I inspected the requested [NBC Sports NBA Player News page](https://www.nbcsports.com/fantasy/basketball/player-news). It is a live player-news page with player cards and category labels. The page path itself is not disallowed in the current [NBC Sports robots.txt](https://www.nbcsports.com/robots.txt), though `/api/` and the delivery GraphQL routes are disallowed for general crawlers. More decisively, NBC's [Terms of Use, section 2](https://www.nbcsports.com/terms-use) says users may not use any robot, spider, crawler, or other data-gathering or extraction tool, automated or manual, to access, copy, monitor, scrape, or aggregate service content; it also restricts copying/archiving and incorporating content into an app without advance written permission. Therefore this proof does **not** scrape NBC page HTML or inspect/call its underlying data endpoints. The requested NBC page is technically viewable, but an automated NBC ingestion path is not appropriate without written authorization or a publisher-designated licensed feed.

RotoWire's RSS route is a practical alternative for personal feed-reader use and its published RSS guidance expressly describes use in blogs/personal websites. That wording does not clearly grant broader rights to embed, persist, redistribute, or power a separate fantasy assistant. Keep the current manual proof private and minimal; obtain written permission or a syndication license before production use beyond the publisher's described RSS use. RotoWire's site footer also notes restrictions on commercial use/distribution of third-party data.

## Other structured options

- **RotoWire API (not tested):** the official reference documents `GET https://api.rotowire.com/Basketball/NBA/News.php` and a news archive endpoint. The shape includes an item ID, timestamp, player, injury, and source note fields, which would be richer and more stable than RSS for future ingestion. The docs expose a `key` credential field and login, so this is not an unauthenticated public-data route; access and licensing would need to be arranged first. [NBA News API reference](https://rotowire.readme.io/reference/get_basketball-nba-news-php) · [NBA News Archive reference](https://rotowire.readme.io/reference/get_basketball-nba-news-archive-php).
- **NBA official injury reports (useful current-status complement, not a player-news substitute):** NBA Official says teams report injury, illness, medical-condition, and rest statuses, and reports update continually through the day. Its page links timestamped report PDFs. Use these reports as a separate authoritative current-status source, never infer current availability from an older fantasy-news event. [NBA Injury Report](https://official.nba.com/nba-injury-report-2025-26-season/).
- **Underdog (manual-only fallback found):** its official help page directs users to sport-specific news accounts on X for player news, but I found no documented public RSS/API route there. It may be useful for a human alert workflow; this pass did not automate or ingest social posts. [Underdog News Feed help](https://help.underdogsports.com/en/articles/11144954-news-feed).

## Run it

From the repository root, run:

```sh
python3 research/news_pipeline/refresh.py
```

The script uses only Python's standard library and fetches the publisher-provided RSS URL. `--feed-file PATH` supports offline replay of an already retrieved XML fixture for dedup/correction checks. Persistent output defaults to `research/news_pipeline/data/news.json`; a compact example projection is written to `research/news_pipeline/data/sample_records.json`. `research/news_pipeline/player_aliases.json` is a small local override map; canonical player identity is matched against `research/rosters_injuries/rosters_2026-27.csv`. RotoWire numeric profile IDs are retained separately and are not misrepresented as ESPN/NBA IDs.

## Production gaps

This is a feasibility probe, not a deployed ingestion service. Before production refresh, the remaining work is:

1. Get written rights for the intended private-app storage/display/redistribution scope, especially before using NBC or moving beyond RotoWire's documented RSS use.
2. Confirm RSS item retention and update behavior over a full season. The tested feed contained five items and is not a complete archive; use a licensed API if historical coverage or richer correction semantics are needed.
3. Add scheduled execution only after approval, with backoff, timeout/HTTP conditional requests, run locking, source-health alerts, and a bounded retention policy.
4. Add a review queue for new aliases/unmatched players, test names with suffixes/diacritics/transliterations, and ensure local roster IDs are refreshed at season boundaries.
5. Ingest current official NBA injury statuses separately with report timestamp and source; track event history independently from current status so stale items cannot keep players marked injured.
6. Decide storage rights and retention for source metadata/hashes and revision logs; add a durable database/unique constraint if this moves beyond a local JSON proof.

No recurring job, account, paid API, login credential, extension, league write, or automation was created.
