const DEFAULT_LEAGUE_ID = "9490871";
const DEFAULT_SEASON = "2026";
const ESPN_API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons";

function makeLeagueUrl(leagueId, season) {
  const url = new URL(`${ESPN_API}/${season}/segments/0/leagues/${leagueId}`);
  for (const view of ["mTeam", "mRoster", "mSettings", "mStandings"]) {
    url.searchParams.append("view", view);
  }
  return url;
}

export async function fetchLeague({
  leagueId = process.env.ESPN_LEAGUE_ID ?? DEFAULT_LEAGUE_ID,
  season = process.env.ESPN_SEASON ?? DEFAULT_SEASON,
  swid = process.env.ESPN_SWID,
  espnS2 = process.env.ESPN_S2,
} = {}) {
  if (!/^\d+$/.test(String(leagueId))) {
    throw new Error("ESPN_LEAGUE_ID must be a numeric league ID.");
  }
  if (!/^\d{4}$/.test(String(season))) {
    throw new Error("ESPN_SEASON must be a four-digit year.");
  }

  const headers = { Accept: "application/json" };
  const cookies = [];
  if (swid) cookies.push(`SWID=${swid}`);
  if (espnS2) cookies.push(`espn_s2=${espnS2}`);
  if (cookies.length) headers.Cookie = cookies.join("; ");

  const response = await fetch(makeLeagueUrl(String(leagueId), String(season)), { headers });
  if (response.status === 401 || response.status === 403) {
    throw new Error("ESPN denied access. For a private league, set ESPN_SWID and ESPN_S2 locally.");
  }
  if (response.status === 404) {
    throw new Error(`League ${leagueId} was not found for season ${season}. Check the league ID and season.`);
  }
  if (!response.ok) {
    throw new Error(`ESPN API request failed (${response.status} ${response.statusText}).`);
  }
  return response.json();
}

export function summarizeLeague(league) {
  const teams = (league.teams ?? []).map((team) => {
    const roster = team.roster?.entries ?? [];
    return {
      id: team.id,
      name: team.name || [team.location, team.nickname].filter(Boolean).join(" ") || `Team ${team.id}`,
      record: team.record?.overall
        ? {
            wins: team.record.overall.wins,
            losses: team.record.overall.losses,
            ties: team.record.overall.ties,
          }
        : undefined,
      rosterSize: roster.length,
    };
  });

  return {
    leagueId: league.id,
    season: league.seasonId,
    name: league.settings?.name,
    public: league.settings?.isPublic,
    scoringType: league.settings?.scoringSettings?.scoringType,
    teams,
  };
}

if (import.meta.url === new URL(process.argv[1], "file:").href) {
  try {
    const league = await fetchLeague();
    process.stdout.write(`${JSON.stringify(summarizeLeague(league), null, 2)}\n`);
  } catch (error) {
    console.error(`Could not load ESPN league: ${error.message}`);
    process.exitCode = 1;
  }
}
