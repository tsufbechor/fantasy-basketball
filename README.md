# Fantasy Basketball AI Assistant

First milestone: read league settings, standings, and rosters from ESPN Fantasy Basketball.

This uses ESPN's undocumented Fantasy API. Your league (ID `9490871`) was reachable through the read endpoint for season 2026 without login during setup; ESPN marked it public. The response included 12 teams and head-to-head category scoring. The endpoint can change without notice.

## Run

Requires Node.js 18 or newer.

```sh
cp .env.example .env
npm run league
```

The script reads `ESPN_LEAGUE_ID` and `ESPN_SEASON` from the environment (defaults are this league and season 2026). It prints a compact JSON summary of league settings, teams, records, and roster sizes. The exported `fetchLeague()` function returns the full ESPN response, including rosters, for the assistant layer to consume.

If ESPN later makes the league private, set `ESPN_SWID` and `ESPN_S2` in your local environment. These are account cookies: never paste them into chat, commit them, or share them. The `.env` file is ignored by Git.

The reusable `fetchLeague()` and `summarizeLeague()` functions are exported from `src/espn-league.mjs` for the next assistant/API layer.
