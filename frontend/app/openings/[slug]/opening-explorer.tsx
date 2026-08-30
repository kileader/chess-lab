'use client';

import { useState } from 'react';
import { apiFetch } from '../../../lib/api-client';
import { ChessBoard } from '../../chess-board';
import { SavePracticePosition } from './save-practice-position';

type Results = { games: number; wins: number; draws: number; losses: number; unfinished: number; score: number | null };
type Reply = Results & {
  san: string; uci: string; frequency: number; score_change: number | null;
  examples: Array<{ date: string | null; source_url: string | null; result: string | null }>;
};
export type ExplorerData = Results & {
  fen: string; san_path: string[]; root_plies: number;
  turn: 'white' | 'black'; player_color: 'white' | 'black';
  ended_games: number; skipped_games: number; at_limit: boolean; moves: Reply[];
};

const percent = (score: number | null) => score === null ? '—' : `${(score * 100).toFixed(1)}%`;

export function OpeningExplorer({ initialData, family, userId, dateFrom, dateTo, initialColor, initialLine }: {
  initialData: ExplorerData | null; family: string; userId: number;
  dateFrom?: string; dateTo?: string; initialColor: 'white' | 'black'; initialLine: string[];
}) {
  const [data, setData] = useState(initialData);
  const [color, setColor] = useState(initialColor);
  const [line, setLine] = useState<string[]>(initialLine);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const busy = loading || saving;
  const [error, setError] = useState<string | null>(null);

  async function navigate(nextLine: string[], nextColor = color) {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({ family, color: nextColor, line: nextLine.join(',') });
      if (dateFrom) query.set('date_from', dateFrom);
      if (dateTo) query.set('date_to', dateTo);
      const response = await apiFetch(`/api/users/${userId}/openings/explorer?${query}`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Could not load this position. Your previous position has been kept.');
      const nextData = await response.json() as ExplorerData;
      setData(nextData);
      setLine(nextLine);
      setColor(nextColor);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not load this position.');
    } finally { setLoading(false); }
  }

  const concern = data?.moves.filter((reply) => reply.wins + reply.draws + reply.losses >= 8 && (reply.score_change ?? 0) <= -0.1)
    .sort((left, right) => (left.score_change ?? 0) - (right.score_change ?? 0))[0];
  const frequent = data?.moves[0];
  return <section id="explorer" className="panel explorer-panel" aria-labelledby="explorer-title" aria-busy={busy}>
    <div className="explorer-heading">
      <div><p className="eyebrow">Follow the positions</p><h2 id="explorer-title">Your opening explorer</h2></div>
      <label>Explore your games as <select value={color} disabled={busy} onChange={(event) => void navigate([], event.target.value as 'white' | 'black')}><option value="white">White</option><option value="black">Black</option></select></label>
    </div>
    <p className="explorer-note">Starts where {family} is defined. Click a move to see the next replies. Dates follow this page; the color selector applies to this explorer only.</p>
    {error && <p role="alert" className="explorer-error">{error} <button disabled={loading} onClick={() => void navigate(line)}>Retry</button></p>}
    {!data ? <div className="explorer-empty"><p>Opening explorer data is unavailable.</p><button disabled={loading} onClick={() => void navigate([])}>{loading ? 'Loading…' : 'Load explorer'}</button></div> : <>
      <div className="explorer-layout">
        <div>
          <ChessBoard fen={data.fen} color={color} />
          <div className="explorer-navigation"><button disabled={busy || !line.length} onClick={() => void navigate(line.slice(0, -1))}>← Back</button><button disabled={busy || !line.length} onClick={() => void navigate([])}>Opening start</button></div>
          <p className="explorer-turn">{data.turn === 'white' ? 'White' : 'Black'} to move · {data.turn === color ? 'your turn' : 'opponent’s turn'}</p>
          <SavePracticePosition key={`${data.fen}-${color}`} family={family} userId={userId} line={line} color={color} turn={data.turn} dateFrom={dateFrom} dateTo={dateTo} disabled={loading} onSavingChange={setSaving} />
        </div>
        <div className="explorer-results">
          <nav className="explorer-path" aria-label="Explored move line">{data.san_path.map((move, index) => {
            const label = `${index % 2 === 0 ? `${Math.floor(index / 2) + 1}. ` : ''}${move}`;
            return index < data.root_plies ? <span key={index}>{label}</span> : <button key={index} disabled={busy} aria-current={index === data.san_path.length - 1 ? 'step' : undefined} onClick={() => void navigate(line.slice(0, index - data.root_plies + 1))}>{label}</button>;
          })}</nav>
          <p className="explorer-summary" role="status">{loading ? 'Loading position…' : `${data.games} games reached this position · ${percent(data.score)} final-game score for you`}</p>
          <h3>{data.turn === color ? 'What you usually play' : 'Replies you face'}</h3>
          {frequent && <p className="explorer-note">{frequent.san} is most frequent: {frequent.games} games ({(frequent.frequency * 100).toFixed(1)}% of this position’s games).</p>}
          {concern && <p className="explorer-concern">Worth reviewing: after {concern.san}, your final-game score is {percent(concern.score)} across {concern.games} games—{Math.abs(concern.score_change! * 100).toFixed(1)} points below this position’s overall score. This does not establish that the move caused the result.</p>}
          {!data.games && <p>No games as {color === 'white' ? 'White' : 'Black'} reached this position in the selected dates. Try the other color or go back.</p>}
          {!!data.games && !data.moves.length && <p>No further recorded moves from this position.</p>}
          <div className="explorer-move-list">{data.moves.map((reply) => <div className="explorer-reply" key={reply.uci}>
            <button className="explorer-move" disabled={busy || data.at_limit} onClick={() => void navigate([...line, reply.uci])} aria-label={`Explore ${reply.san}, ${reply.games} games, ${percent(reply.score)} score`}>
              <strong>{reply.san}</strong><span>{reply.games} games · {(reply.frequency * 100).toFixed(1)}%<small>{reply.wins}W {reply.draws}D {reply.losses}L{reply.unfinished ? ` · ${reply.unfinished} unfinished` : ''}</small></span>
              <span>{percent(reply.score)} score<small>{reply.score_change === null ? 'No completed games' : `${reply.score_change >= 0 ? '+' : ''}${(reply.score_change * 100).toFixed(1)} pts vs position`}{reply.wins + reply.draws + reply.losses < 8 ? ' · small sample' : ''}</small></span>
            </button>
            {reply.examples.some((example) => example.source_url && /^https?:\/\//i.test(example.source_url)) && <details><summary>Example games</summary>{reply.examples.filter((example) => example.source_url && /^https?:\/\//i.test(example.source_url)).map((example, index) => <a key={index} href={example.source_url!} target="_blank" rel="noreferrer">{example.date ?? 'Undated'} · {example.result ?? 'Unfinished'} ↗</a>)}</details>}
          </div>)}</div>
          {data.at_limit && <p>Exploration stops 24 half-moves past the opening start. Use an example game to continue.</p>}
          {!!data.ended_games && <p className="explorer-note">{data.ended_games} game(s) end at this position, so reply percentages may total less than 100%.</p>}
        </div>
      </div>
      <p className="explorer-footnote">Counts include transpositions and games later classified under another opening. Each game counts once at a position, within its first 40 moves. Scores include ½ point per draw and exclude unfinished games. They measure final results, not move quality.{data.skipped_games ? ` ${data.skipped_games} malformed PGN record(s) were excluded.` : ''}</p>
    </>}
  </section>;
}
