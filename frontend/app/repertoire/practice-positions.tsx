'use client';

import Link from 'next/link';
import { apiFetch } from '../../lib/api-client';
import { useState, type FormEvent } from 'react';
import { ChessBoard } from '../chess-board';
import { practiceError, practicePositionHref, type PracticePosition } from '../practice-position';


function SavedPosition({ item, userId, onUpdate, onRemove }: {
  item: PracticePosition; userId: number;
  onUpdate: (item: PracticePosition) => void; onRemove: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [note, setNote] = useState(item.note);
  const [move, setMove] = useState(item.candidate_move);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const turn = item.fen.split(' ')[1] === 'w' ? 'White' : 'Black';

  async function save(event: FormEvent) {
    event.preventDefault();
    setPending(true); setError(null);
    try {
      const response = await apiFetch(`/api/users/${userId}/practice-positions/${item.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note, candidate_move: move }),
      });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not update this position.'));
      onUpdate(await response.json() as PracticePosition);
      setEditing(false);
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not update this position.'); }
    finally { setPending(false); }
  }

  async function remove() {
    setPending(true); setError(null);
    try {
      const response = await apiFetch(`/api/users/${userId}/practice-positions/${item.id}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not remove this position.'));
      onRemove(item.id);
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not remove this position.'); }
    finally { setPending(false); }
  }

  return <article className="saved-position" id={`practice-position-${item.id}`} aria-busy={pending}>
    <div className="saved-position-board"><ChessBoard fen={item.fen} color={item.player_color} /></div>
    <div className="saved-position-content">
      <p className="eyebrow">You play {item.player_color} · {turn} to move</p>
      <h3>{item.family}</h3>
      <p className="saved-position-line">{item.san_path.map((san, index) => `${index % 2 === 0 ? `${Math.floor(index / 2) + 1}. ` : ''}${san}`).join(' ')}</p>
      {editing ? <form className="position-form" onSubmit={(event) => void save(event)}>
        <label>Your note (optional)<textarea rows={3} maxLength={1000} value={note} disabled={pending} onChange={(event) => setNote(event.target.value)} /></label>
        <label>Move to try for {turn} (optional)<input maxLength={20} value={move} disabled={pending} onChange={(event) => setMove(event.target.value)} placeholder="e.g. Nf3" /></label>
        <div className="position-actions"><button disabled={pending} type="submit">{pending ? 'Saving…' : 'Save changes'}</button><button disabled={pending} type="button" onClick={() => { setEditing(false); setError(null); }}>Cancel</button></div>
      </form> : <>
        <p className="saved-position-note">{item.note || 'No note yet.'}</p>
        {item.candidate_move && <p>Move to try for {turn}: <strong>{item.candidate_move}</strong></p>}
        <div className="position-actions"><Link href={practicePositionHref(item)}>Return to explorer →</Link><button disabled={pending || removing} onClick={() => { setNote(item.note); setMove(item.candidate_move); setEditing(true); setError(null); }}>Edit note / move</button><button disabled={pending || removing} onClick={() => setRemoving(true)}>Remove</button></div>
      </>}
      {removing && <div className="position-remove-confirm"><p>Remove this saved position? Your imported games stay untouched.</p><div className="position-actions"><button disabled={pending} onClick={() => void remove()}>{pending ? 'Removing…' : 'Remove position'}</button><button disabled={pending} onClick={() => { setRemoving(false); setError(null); }}>Keep it</button></div></div>}
      {error && <p role="alert" className="explorer-error">{error}</p>}
      {item.examples.some((example) => /^https?:\/\//i.test(example.source_url ?? '')) && <div className="saved-position-examples"><span>Example games saved with this position:</span>{item.examples.filter((example) => /^https?:\/\//i.test(example.source_url ?? '')).map((example) => <a key={example.source_url} href={example.source_url!} target="_blank" rel="noreferrer">{example.date || 'Game'} · {example.result || 'Result unknown'} ↗</a>)}</div>}
    </div>
  </article>;
}

export function PracticePositions({ initialItems, userId }: { initialItems: PracticePosition[]; userId: number }) {
  const [items, setItems] = useState(initialItems);
  return <section className="panel practice-positions" id="practice-positions">
    <p className="eyebrow">From your opening explorer</p>
    <h2>Positions to practice</h2>
    <p>Specific boards, your ideas, and the games that brought you there.</p>
    {items.length === 0 ? <p className="practice-empty">Nothing saved yet. <Link href="/#openings">Explore an opening</Link>, then choose “Save this position to practice.”</p> : <div className="saved-position-list">{items.map((item) => <SavedPosition key={item.id} item={item} userId={userId} onUpdate={(updated) => setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry))} onRemove={(id) => setItems((current) => current.filter((entry) => entry.id !== id))} />)}</div>}
  </section>;
}
