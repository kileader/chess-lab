type OpeningOverview = {
  eco: string | null;
  opening: string;
  games: number;
  wins: number;
  draws: number;
  losses: number;
};

type UserOverview = {
  user: {
    id: number;
    display_name: string;
    identities: Array<{ platform: string; username: string }>;
  };
  total_games: number;
  white_games: number;
  black_games: number;
  wins: number;
  draws: number;
  losses: number;
  classified_games: number;
  first_game_date: string | null;
  last_game_date: string | null;
  minimum_rating: number | null;
  maximum_rating: number | null;
  top_openings: OpeningOverview[];
};

type GameSummary = {
  date: string | null;
  white: string | null;
  black: string | null;
  result: string | null;
  time_control: string | null;
  opening: string | null;
  source_url: string | null;
};

type GamePage = {
  games: GameSummary[];
};

type FirstMoveResponse = {
  reply: string;
  games: number;
  wins: number;
  draws: number;
  losses: number;
};

type AnalysisFilters = {
  date_from?: string;
  date_to?: string;
  color?: 'white' | 'black';
  grouping: 'family' | 'variation';
};

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const apiBase = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';

async function loadOverview(
  filters: AnalysisFilters,
  openingLimit = 10,
): Promise<UserOverview | null> {
  try {
    const query = new URLSearchParams();
    if (filters.date_from) query.set('date_from', filters.date_from);
    if (filters.date_to) query.set('date_to', filters.date_to);
    if (filters.color) query.set('color', filters.color);
    query.set('grouping', filters.grouping);
    query.set('opening_limit', String(openingLimit));
    const response = await fetch(`${apiBase}/api/users/1/overview?${query}`, {
      cache: 'no-store',
    });
    if (!response.ok) return null;
    return response.json() as Promise<UserOverview>;
  } catch {
    return null;
  }
}

async function loadRecentGames(): Promise<GameSummary[]> {
  try {
    const response = await fetch(`${apiBase}/api/games?limit=8&offset=0`, {
      cache: 'no-store',
    });
    if (!response.ok) return [];
    const page = await response.json() as GamePage;
    return page.games;
  } catch {
    return [];
  }
}

async function loadFirstMoveResponses(filters: AnalysisFilters): Promise<FirstMoveResponse[]> {
  if (filters.color === 'black') return [];
  try {
    const query = new URLSearchParams({ first_move: 'e4' });
    if (filters.date_from) query.set('date_from', filters.date_from);
    if (filters.date_to) query.set('date_to', filters.date_to);
    if (filters.color) query.set('color', filters.color);
    const response = await fetch(`${apiBase}/api/users/1/responses?${query}`, { cache: 'no-store' });
    return response.ok ? response.json() as Promise<FirstMoveResponse[]> : [];
  } catch {
    return [];
  }
}

function scorePercent(wins: number, draws: number, games: number) {
  return games ? ((wins + draws / 2) / games) * 100 : 0;
}

function formatDate(value: string | null) {
  if (!value) return 'Unknown';
  const [year, month, day] = value.split('.').map(Number);
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    year: 'numeric',
    day: 'numeric',
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

function apiDate(date: Date) {
  return date.toISOString().slice(0, 10).replaceAll('-', '.');
}

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function parseApiDate(value: string) {
  const [year, month, day] = value.split('.').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function comparisonPeriod(startValue: string | undefined, endValue: string | null | undefined) {
  if (!startValue || !endValue) return null;
  const start = parseApiDate(startValue);
  const end = parseApiDate(endValue);
  const days = Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1;
  if (days < 1) return null;
  const previousEnd = new Date(start);
  previousEnd.setUTCDate(previousEnd.getUTCDate() - 1);
  const previousStart = new Date(previousEnd);
  previousStart.setUTCDate(previousStart.getUTCDate() - days + 1);
  return { date_from: apiDate(previousStart), date_to: apiDate(previousEnd), days };
}

export default async function Home({ searchParams }: PageProps) {
  const params = await searchParams;
  const ninetyDaysAgo = new Date();
  ninetyDaysAgo.setUTCDate(ninetyDaysAgo.getUTCDate() - 90);
  const period = firstValue(params.period);
  const filters: AnalysisFilters = {
    date_from: period === 'all' ? undefined : firstValue(params.date_from) ?? apiDate(ninetyDaysAgo),
    date_to: firstValue(params.date_to),
    color: firstValue(params.color) === 'white' || firstValue(params.color) === 'black'
      ? firstValue(params.color) as 'white' | 'black'
      : undefined,
    grouping: firstValue(params.grouping) === 'variation' ? 'variation' : 'family',
  };
  const [overview, lifetimeOverview, recentGames, firstMoveResponses] = await Promise.all([
    loadOverview(filters),
    loadOverview({ grouping: 'family' }),
    loadRecentGames(),
    loadFirstMoveResponses(filters),
  ]);

  if (!overview || !lifetimeOverview) {
    return (
      <main className="connection-shell">
        <section className="connection-card">
          <div className="brand-mark" aria-hidden="true">CL</div>
          <p className="eyebrow">Chess Lab</p>
          <h1>Your chess data is waiting.</h1>
          <p>Start the local Chess Lab API, then refresh this page to load your dashboard.</p>
        </section>
      </main>
    );
  }

  const overallScore = scorePercent(
    overview.wins,
    overview.draws,
    overview.total_games,
  );
  const identity = overview.user.identities[0];
  const detailQuery = new URLSearchParams();
  if (filters.date_from) detailQuery.set('date_from', filters.date_from);
  if (filters.date_to) detailQuery.set('date_to', filters.date_to);
  if (filters.color) detailQuery.set('color', filters.color);
  if (period === 'all') detailQuery.set('period', 'all');
  const minYear = Number(lifetimeOverview.first_game_date?.slice(0, 4)) || new Date().getFullYear();
  const maxYear = Number(lifetimeOverview.last_game_date?.slice(0, 4)) || new Date().getFullYear();
  const priorPeriod = comparisonPeriod(
    filters.date_from,
    overview.last_game_date,
  );
  const practiceOverview = await loadOverview({ ...filters, grouping: 'family' }, 50);
  const priorOverview = priorPeriod
    ? await loadOverview({
        date_from: priorPeriod.date_from,
        date_to: priorPeriod.date_to,
        color: filters.color,
        grouping: 'family',
      }, 50)
    : null;
  const priorOpenings = new Map(
    priorOverview?.top_openings.map((opening) => [opening.opening, opening]) ?? [],
  );
  const comparisonOpenings = (practiceOverview?.top_openings ?? []).map((opening) => {
    const prior = priorOpenings.get(opening.opening);
    const currentScore = scorePercent(opening.wins, opening.draws, opening.games);
    const priorScore = prior
      ? scorePercent(prior.wins, prior.draws, prior.games)
      : null;
    return { ...opening, currentScore, prior, priorScore, change: priorScore === null ? null : currentScore - priorScore };
  });
  const practiceTargets = comparisonOpenings
    .filter((opening) => opening.games >= 12 && (
      opening.currentScore < 45 || (opening.prior && opening.prior.games >= 8 && (opening.change ?? 0) <= -5)
    ))
    .sort((left, right) => left.currentScore - right.currentScore || right.games - left.games)
    .slice(0, 3);
  const dropTargets = filters.color === 'black'
    ? comparisonOpenings
      .filter((opening) => opening.games >= 12)
      .sort((left, right) => left.currentScore - right.currentScore || right.games - left.games)
      .slice(0, 3)
    : [];
  const practiceReason = (opening: typeof comparisonOpenings[number]) => {
    if (opening.change !== null && opening.change <= -5) {
      return `${Math.abs(opening.change).toFixed(1)} points worse than before`;
    }
    return 'Your results are low';
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Chess Lab home">
          <span className="brand-mark">CL</span>
          <span>Chess Lab</span>
        </a>
        <nav aria-label="Primary navigation">
          <a className="nav-active" href="#overview">Overview</a>
          <a href="#openings">Openings</a>
          <a href="/repertoire">Repertoire</a>
          <a href="#games">Games</a>
          <a href="#upload">Import</a>
        </nav>
        <div className="profile-pill">
          <span className="status-dot" />
          <span>{identity?.username ?? overview.user.display_name}</span>
          <small>{identity?.platform.replace('_', '.') ?? 'local'}</small>
        </div>
      </header>

      <div className="dashboard" id="top">
        <section className="hero" id="overview">
          <div>
            <p className="eyebrow">Personal performance archive</p>
            <h1>See the patterns<br />behind your play.</h1>
            <p className="hero-copy">
              {overview.total_games.toLocaleString()} games, organized around the
              openings you trust and the positions that test you.
            </p>
          </div>
          <div className="hero-range" aria-label="Archive date range">
            <span>Archive</span>
            <strong>{formatDate(overview.first_game_date)}</strong>
            <i aria-hidden="true" />
            <strong>{formatDate(overview.last_game_date)}</strong>
          </div>
        </section>

        <ScopeControls
          color={filters.color ?? 'all'}
          dateFrom={filters.date_from}
          dateTo={filters.date_to}
          filteredGames={overview.total_games}
          grouping={filters.grouping}
          maxYear={maxYear}
          minYear={minYear}
          totalGames={lifetimeOverview.total_games}
        />

        <section className="stat-grid" aria-label="Performance summary">
          <article className="stat-card stat-primary">
            <p>Overall score</p>
            <strong>{overallScore.toFixed(1)}<small>%</small></strong>
            <span>{overview.wins.toLocaleString()} wins · {overview.draws} draws</span>
          </article>
          <article className="stat-card">
            <p>Games recorded</p>
            <strong>{overview.total_games.toLocaleString()}</strong>
            <span>{overview.classified_games.toLocaleString()} opening-classified</span>
          </article>
          <article className="stat-card">
            <p>Rating span</p>
            <strong>{overview.minimum_rating}—{overview.maximum_rating}</strong>
            <span>Across all time controls</span>
          </article>
        </section>

        {firstMoveResponses.length > 0 && <section className="panel response-panel" aria-labelledby="responses-title">
          <div className="panel-heading"><div><p className="eyebrow">As White</p><h2 id="responses-title">What you face after 1.e4</h2></div><span className="panel-note">Within your selected time window</span></div>
          <div className="response-list">{firstMoveResponses.map((response) => {
            const responseScore = scorePercent(response.wins, response.draws, response.games);
            return <div className="response-row" key={response.reply}><strong>1…{response.reply}</strong><span>{response.games} games</span><span>{responseScore.toFixed(1)}% score</span><i aria-hidden="true"><b style={{ width: `${response.games / firstMoveResponses[0].games * 100}%` }} /></i></div>;
          })}</div>
        </section>}

        {practiceOverview && (
          <section className={`practice-panel panel ${dropTargets.length ? '' : 'practice-panel-single'}`} aria-labelledby="practice-title">
            <div className="panel-heading">
              <div><p className="eyebrow">What to work on</p><h2 id="practice-title">Practice or replace</h2></div>
              <span className="panel-note">{priorPeriod ? `Compared with the preceding ${priorPeriod.days} days` : 'Based on the selected period'}</span>
            </div>
            <div className="practice-grid">
              <div className="practice-column">
                <p className="eyebrow">Practice now</p>
                {practiceTargets.length ? practiceTargets.map((opening) => (
                  <a className="practice-row" href={`/openings/${encodeURIComponent(opening.opening)}${detailQuery.size ? `?${detailQuery}` : ''}`} key={opening.opening}>
                    <span className="eco-badge">{opening.eco ?? '—'}</span>
                    <span><strong>{opening.opening}</strong><small>{opening.games} games · {opening.currentScore.toFixed(1)}% score</small></span>
                    <b className="trend-down">{practiceReason(opening)}</b>
                  </a>
                )) : <p className="practice-empty">No opening family has both a meaningful sample and a clear concern signal in this period.</p>}
              </div>
              {dropTargets.length > 0 && <div className="practice-column practice-drop">
                <p className="eyebrow">Openings you could replace</p>
                {dropTargets.map((opening) => (
                    <a className="practice-row" href={`/openings/${encodeURIComponent(opening.opening)}${detailQuery.size ? `?${detailQuery}` : ''}`} key={opening.opening}>
                      <span className="eco-badge">{opening.eco ?? '—'}</span>
                      <span><strong>{opening.opening}</strong><small>{opening.games} games · {opening.currentScore.toFixed(1)}% score{opening.priorScore === null ? '' : ` · ${opening.priorScore.toFixed(1)}% prior`}</small></span>
                      <b className="trend-down">See details</b>
                    </a>
                  ))}
              </div>}
            </div>
          </section>
        )}

        <section className="content-grid" id="openings">
          <article className="panel openings-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Repertoire fingerprint</p>
                <h2>Most played {filters.grouping === 'family' ? 'families' : 'variations'}</h2>
              </div>
              <span className="panel-note">Score includes ½ point per draw</span>
            </div>

            <div className="opening-list">
              {overview.top_openings.map((opening, index) => {
                const score = scorePercent(opening.wins, opening.draws, opening.games);
                const family = opening.opening.split(':', 1)[0];
                return (
                  <a
                    className="opening-row"
                    href={`/openings/${encodeURIComponent(family)}${detailQuery.size ? `?${detailQuery}` : ''}`}
                    key={`${opening.eco}-${opening.opening}`}
                    aria-label={`Analyze ${family}`}
                  >
                    <span className="opening-rank">{String(index + 1).padStart(2, '0')}</span>
                    <span className="eco-badge">{opening.eco ?? '—'}</span>
                    <div className="opening-name">
                      <strong>{opening.opening}</strong>
                      <span>{opening.games} games · {opening.wins}W {opening.draws}D {opening.losses}L</span>
                    </div>
                    <div className="score-cell">
                      <strong>{score.toFixed(1)}%</strong>
                      <span className="score-track" aria-hidden="true">
                        <i style={{ width: `${score}%` }} />
                      </span>
                    </div>
                  </a>
                );
              })}
            </div>
          </article>

          <aside className="insight-stack">
            <article className="panel insight-card insight-dark">
              <p className="eyebrow">Repertoire anchor</p>
              <h2>Caro-Kann</h2>
              <p>Your most familiar defensive structure, with 1,376 games as Black across the family.</p>
              <div className="mini-board" aria-hidden="true">
                {Array.from({ length: 16 }, (_, index) => <span key={index} />)}
              </div>
            </article>
            <article className="panel insight-card">
              <p className="eyebrow">Sharpest edge</p>
              <h2>Fried Liver Attack</h2>
              <strong className="insight-number">72.9%</strong>
              <p>Score across 133 games—your clearest high-performing tactical line.</p>
            </article>
          </aside>
        </section>

        <section className="games-grid" id="games">
          <article className="panel recent-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Latest from the archive</p>
                <h2>Recent games</h2>
              </div>
              <span className="panel-note">Newest imports first</span>
            </div>
            <div className="game-list">
              {recentGames.map((game, index) => {
                const username = identity?.username.toLowerCase();
                const isWhite = game.white?.toLowerCase() === username;
                const won = (isWhite && game.result === '1-0') || (!isWhite && game.result === '0-1');
                const drew = game.result === '1/2-1/2';
                const outcome = drew ? 'Draw' : won ? 'Win' : 'Loss';
                return (
                  <a className="game-row" href={game.source_url ?? '#'} key={`${game.source_url}-${index}`} target={game.source_url ? '_blank' : undefined}>
                    <span className={`outcome outcome-${outcome.toLowerCase()}`}>{outcome[0]}</span>
                    <div className="matchup">
                      <strong>{game.white ?? 'Unknown'} <i>vs</i> {game.black ?? 'Unknown'}</strong>
                      <span>{game.opening ?? 'Unclassified opening'}</span>
                    </div>
                    <span className="game-meta">{game.time_control ?? '—'}</span>
                    <span className="game-meta">{game.date ?? '—'}</span>
                  </a>
                );
              })}
            </div>
          </article>

          <aside className="panel import-panel" id="upload">
            <p className="eyebrow">Keep the archive current</p>
            <h2>Import games</h2>
            <p>Add a Lichess, Chess.com, or standard PGN archive. Existing games are skipped automatically.</p>
            <UploadForm />
          </aside>
        </section>

        <footer>
          <span>Chess Lab · Local analysis</span>
          <span>{overview.user.display_name}&apos;s archive</span>
        </footer>
      </div>
    </main>
  );
}
import { UploadForm } from './upload-form';
import { ScopeControls } from './scope-controls';
