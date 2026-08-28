import type { Metadata } from 'next';

type ResultBreakdown = {
  games: number;
  wins: number;
  draws: number;
  losses: number;
};

type OpeningDetail = ResultBreakdown & {
  family: string;
  user: {
    display_name: string;
    identities: Array<{ platform: string; username: string }>;
  };
  colors: Array<ResultBreakdown & { color: 'white' | 'black' }>;
  variations: Array<ResultBreakdown & { eco: string | null; opening: string }>;
  years: Array<ResultBreakdown & { year: string }>;
  recent_games: Array<{
    date: string | null;
    white: string | null;
    black: string | null;
    result: string | null;
    time_control: string | null;
    opening: string | null;
    source_url: string | null;
    player_color: 'white' | 'black';
  }>;
};

type OpeningTheory = {
  reference_opening: string;
  player_centipawns: number;
  verdict: string;
};

type OpeningReview = {
  source_url: string | null;
  move: string | null;
  move_number: number | null;
  centipawns_lost: number | null;
};

type PageProps = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};
const apiBase = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';

function score(data: ResultBreakdown) {
  return data.games ? ((data.wins + data.draws / 2) / data.games) * 100 : 0;
}

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

async function loadDetail(family: string, filters: URLSearchParams): Promise<OpeningDetail | null> {
  try {
    const query = new URLSearchParams(filters);
    query.set('family', family);
    const response = await fetch(
      `${apiBase}/api/users/1/openings/detail?${query}`,
      { cache: 'no-store' },
    );
    if (!response.ok) return null;
    return response.json() as Promise<OpeningDetail>;
  } catch {
    return null;
  }
}

async function loadTheory(family: string, filters: URLSearchParams): Promise<OpeningTheory | null> {
  try {
    const query = new URLSearchParams(filters);
    query.set('family', family);
    const response = await fetch(`${apiBase}/api/users/1/openings/theory?${query}`, { cache: 'no-store' });
    if (!response.ok) return null;
    return response.json() as Promise<OpeningTheory>;
  } catch {
    return null;
  }
}

async function loadReviews(family: string, filters: URLSearchParams): Promise<OpeningReview[]> {
  try {
    const query = new URLSearchParams(filters);
    query.set('family', family);
    const response = await fetch(`${apiBase}/api/users/1/openings/review?${query}`, { cache: 'no-store' });
    return response.ok ? response.json() as Promise<OpeningReview[]> : [];
  } catch { return []; }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const family = decodeURIComponent(slug);
  return {
    title: `${family} analysis · Chess Lab`,
    description: `Color, variation, yearly, and recent-game analysis for ${family}.`,
    openGraph: { images: [] },
    twitter: { images: [] },
  };
}

export default async function OpeningPage({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const family = decodeURIComponent(slug);
  const rawSearchParams = await searchParams;
  const filters = new URLSearchParams();
  const dateFrom = firstValue(rawSearchParams.date_from);
  const dateTo = firstValue(rawSearchParams.date_to);
  const color = firstValue(rawSearchParams.color);
  const period = firstValue(rawSearchParams.period);
  if (dateFrom) filters.set('date_from', dateFrom);
  if (dateTo) filters.set('date_to', dateTo);
  if (color === 'white' || color === 'black') filters.set('color', color);
  const [detail, theory, reviews] = await Promise.all([loadDetail(family, filters), loadTheory(family, filters), loadReviews(family, filters)]);
  const overviewFilters = new URLSearchParams(filters);
  if (period === 'all') overviewFilters.set('period', 'all');
  const overviewHref = `/${overviewFilters.size ? `?${overviewFilters}` : ''}#openings`;

  if (!detail) {
    return (
      <main className="connection-shell">
        <section className="connection-card">
          <div className="brand-mark" aria-hidden="true">CL</div>
          <p className="eyebrow">Opening analysis</p>
          <h1>No games found.</h1>
          <p>Chess Lab could not find games in the {family} family. Return to the overview and choose another opening.</p>
          <a className="back-link" href={overviewHref}>← Back to overview</a>
        </section>
      </main>
    );
  }

  const white = detail.colors.find((item) => item.color === 'white');
  const black = detail.colors.find((item) => item.color === 'black');
  const identity = detail.user.identities[0];
  const losses = detail.recent_games.filter((game) => (
    (game.player_color === 'white' && game.result === '0-1')
    || (game.player_color === 'black' && game.result === '1-0')
  ));
  const reviewByUrl = new Map(reviews.map((review) => [review.source_url, review]));

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Chess Lab home">
          <span className="brand-mark">CL</span><span>Chess Lab</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="/#overview">Overview</a>
          <a className="nav-active" href="/#openings">Openings</a>
          <a href="/repertoire">Repertoire</a>
          <a href="/#games">Games</a>
          <a href="/#upload">Import</a>
        </nav>
        <div className="profile-pill">
          <span className="status-dot" />
          <span>{identity?.username ?? detail.user.display_name}</span>
          <small>{identity?.platform.replace('_', '.') ?? 'local'}</small>
        </div>
      </header>

      <div className="detail-shell">
        <a className="back-link" href={overviewHref}>← Back to all openings</a>
        <section className="detail-hero">
          <div><p className="eyebrow">Opening family analysis{color ? ` · as ${color}` : ''}</p><h1>{detail.family}</h1></div>
          <div className="detail-total"><strong>{detail.games.toLocaleString()}</strong><span>games in this family</span></div>
        </section>

        <section className="detail-score-grid" aria-label="Opening results">
          <article className="detail-score detail-score-primary">
            <p>Overall score</p><strong>{score(detail).toFixed(1)}%</strong>
            <span>{detail.wins}W · {detail.draws}D · {detail.losses}L</span>
          </article>
          <article className="detail-score">
            <p>As White</p><strong>{white ? `${score(white).toFixed(1)}%` : '—'}</strong>
            <span>{white ? `${white.games} games · ${white.wins}W ${white.draws}D ${white.losses}L` : 'No games'}</span>
          </article>
          <article className="detail-score">
            <p>As Black</p><strong>{black ? `${score(black).toFixed(1)}%` : '—'}</strong>
            <span>{black ? `${black.games} games · ${black.wins}W ${black.draws}D ${black.losses}L` : 'No games'}</span>
          </article>
        </section>

        {theory && <section className="theory-panel panel">
          <p className="eyebrow">Engine check</p>
          <div><strong>Engine says: {theory.verdict}</strong><span>Based on your most-played line: {theory.reference_opening}</span></div>
        </section>}

        <section className="detail-grid">
          <article className="panel detail-panel">
            <div className="panel-heading"><div><p className="eyebrow">Inside the family</p><h2>Variations</h2></div><span className="panel-note">Sorted by games played</span></div>
            <div>
              {detail.variations.map((variation) => (
                <div className="variation-row" key={`${variation.eco}-${variation.opening}`}>
                  <span className="eco-badge">{variation.eco ?? '—'}</span>
                  <span className="variation-name">{variation.opening}</span>
                  <span className="variation-meta">{variation.games} games</span>
                  <span className="variation-meta">{score(variation).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </article>

          <aside className="panel detail-panel">
            <div className="panel-heading"><div><p className="eyebrow">Performance trend</p><h2>By year</h2></div></div>
            <div className="year-list">
              {detail.years.map((year) => (
                <div className="year-row" key={year.year}>
                  <strong>{year.year}</strong>
                  <div className="year-track" title={`${score(year).toFixed(1)}% score`}><i style={{ width: `${score(year)}%` }} /></div>
                  <span>{score(year).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <section className="panel detail-panel detail-games">
          <div className="panel-heading"><div><p className="eyebrow">Start here</p><h2>Recent losses to review</h2></div><span className="panel-note">Open a game to see what went wrong</span></div>
          <div className="game-list">
            {(losses.length ? losses : detail.recent_games).map((game, index) => {
              const won = (game.player_color === 'white' && game.result === '1-0') || (game.player_color === 'black' && game.result === '0-1');
              const drew = game.result === '1/2-1/2';
              const outcome = drew ? 'Draw' : won ? 'Win' : 'Loss';
              const review = reviewByUrl.get(game.source_url);
              return (
                <a className="game-row" href={game.source_url ?? '#'} key={`${game.source_url}-${index}`} target={game.source_url ? '_blank' : undefined}>
                  <span className={`outcome outcome-${outcome.toLowerCase()}`}>{outcome[0]}</span>
                  <div className="matchup"><strong>{game.white ?? 'Unknown'} <i>vs</i> {game.black ?? 'Unknown'}</strong><span>{review?.move ? `Check move ${review.move_number}: ${review.move} lost about ${(review.centipawns_lost! / 100).toFixed(1)} pawns` : game.opening ?? detail.family}</span></div>
                  <span className="game-meta">{game.time_control ?? '—'}</span><span className="game-meta">{game.date ?? '—'}</span>
                </a>
              );
            })}
          </div>
        </section>

        <footer><span>Chess Lab · Local analysis</span><span>{detail.user.display_name}&apos;s archive</span></footer>
      </div>
    </main>
  );
}
