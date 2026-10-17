# Personal draft board

Open `my-draft-board.html` in Chrome or Edge. It is self-contained and works offline for rankings, watchlist, notes, and manual availability.

- Starts with the top 300 players, in source rank order, from the saved Hashtag 2026–27 projections in `data/consolidated/hashtag_projections_2026_27.csv`. Existing top 200 rankings and backups keep their order, stars, and notes, with the additional 100 appended.
- Each player shows 2025–26 actual and 2026–27 projected Hashtag per-game stats for FG%, FT%, 3PM, PTS, REB, AST, STL, and BLK. FG/FT include made / attempted per game. Category grades come directly from the saved Hashtag HTML, displayed with a dark red-to-green palette. The saved historical table covers 252 of these players; absent rows are labeled, never treated as zero. On narrow screens, scroll each stats table sideways.
- Grab the ⠿ handle beside a player and drag them above or below another player. The insertion line shows where they will land; other players shift and the order saves automatically. Dragging also works in search, position, and watchlist filters, preserving hidden players. Focus a handle and press ↑ / ↓ for keyboard reordering. Rank numbers remain available for long moves.
- Click ☆ to add a target. The Watchlist tab shows targets still available.
- Add notes under each player. Changes save automatically in that browser at that file location.
- Click **Download backup** to preserve your order, stars, and notes as JSON. Use **Import & backup → Restore backup** to transfer them to another browser, file location, or the extension. These locations have separate browser storage.
- “Taken” changes availability manually. “All players” includes drafted players and lets you restore them. Clearing manual corrections returns to ESPN's reported availability.

## ESPN connection

Click **Connect ESPN**. The default league is `9490871`, season `2027`, with a draft scheduled for October 17, 2026 at 11:45 a.m. Israel time (confirmed from ESPN on October 15). ESPN season `2026` is last year's completed draft.

**Live tracking requires the installed extension.** The October 15 mock test confirmed that ESPN's public `mDraftDetail` response can report zero picks while the draft room has completed selections. Standalone HTML is for preparing your rankings; it now labels that API limitation during a live draft.

The extension reads completed-pick messages rendered in the open ESPN basketball draft room. It matches exact ESPN IDs from player headshots and captures round/pick labels. A page observer captures updates, with a one-second heartbeat. The sidebar checks the captured snapshot every two seconds. Both the draft page and board must stay open; background throttling or computer sleep can delay updates. If the reader heartbeat is over ten seconds old, the board stops treating it as a fresh connection.

Open an ESPN draft room, click the extension icon, then **Connect ESPN**. The extension selects the most recently detected draft room. Verify its league ID in the connection message. League settings can also select a league explicitly. Rankings, stars, and notes are shared across mock and real leagues; draft picks and manual corrections are isolated by league and season. Before draft day, close the mock rooms and connect from the real draft page.

If a feed request fails, the board shows an error and preserves the last known picks. A successful check only establishes that ESPN's endpoint responded; it does not independently confirm its live completeness. ESPN's API is undocumented. No ESPN draft actions are automated.

## Sidebar extension

The same board HTML is packaged in `extension/`, with a reader restricted to ESPN basketball draft pages. It was loaded in Chrome with the user's approval on October 15.

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable Developer mode and choose **Load unpacked**.
3. Select this project's `extension` directory.
4. Click the extension icon to open the sidebar beside ESPN.
5. Restore your HTML board's JSON backup to carry over your personal list.

The extension requests local storage, a side panel, access to ESPN's fantasy API host, and a content script on ESPN basketball draft pages. It sends no rankings or notes to a server and does not read account cookies. Reloading an extension invalidates its running page readers; open a new practice draft afterward. Avoid refreshing an ESPN practice-draft page: ESPN returned a blank page when that was tried in the test.

Personal preferences and automatic draft snapshots are saved separately, so live polling cannot overwrite ranking/watchlist edits from another open board. Personal edits synchronize across extension windows. The standalone file and extension still have separate storage; export/restore transfers your list between them.

## Development

Rebuild the packaged HTML and player JSON after changing extension source:

```sh
python3 scripts/build_draft_board.py
node --test tests/draft.test.mjs
```

There is no lint or typecheck configuration in this project. Browser verification covers reorder, persistence, manual availability, extension installation, and live capture: one check showed 38 completed picks and 162 available players. The parser also matched all 158 real pick records captured from another practice run.
