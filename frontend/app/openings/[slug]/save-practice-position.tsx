'use client';

import { useState, type FormEvent } from 'react';
import { apiFetch } from '../../../lib/api-client';
import { practiceError, type PracticePosition } from '../../practice-position';


export function SavePracticePosition({ family, userId, line, color, turn, dateFrom, dateTo, disabled, onSavingChange }: {
  family: string; userId: number; line: string[]; color: 'white' | 'black'; turn: 'white' | 'black';
  dateFrom?: string; dateTo?: string; disabled: boolean; onSavingChange: (saving: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [move, setMove] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ position: PracticePosition; created: boolean } | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    onSavingChange(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/users/${userId}/practice-positions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ family, line, player_color: color, date_from: dateFrom ?? null, date_to: dateTo ?? null, note, candidate_move: move }),
      });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not save this position. Please try again.'));
      setSaved(await response.json() as { position: PracticePosition; created: boolean });
      setOpen(false);
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not save this position.'); }
    finally { setSaving(false); onSavingChange(false); }
  }

  return <div className="save-position">
    {!open && !saved && <button disabled={disabled} onClick={() => setOpen(true)}>Save this position to practice</button>}
    {saved && <p role="status">{saved.created ? 'Saved to your practice list.' : 'Already saved—your existing notes were kept.'} <a href={`/repertoire#practice-position-${saved.position.id}`}>View saved position →</a></p>}
    {open && <form className="position-form" onSubmit={(event) => void save(event)}>
      <label>Your note (optional)<textarea rows={3} maxLength={1000} value={note} disabled={saving} onChange={(event) => setNote(event.target.value)} placeholder="What do you want to understand here?" /></label>
      <label>Move to try for {turn === 'white' ? 'White' : 'Black'} (optional)<input value={move} maxLength={20} disabled={saving} onChange={(event) => setMove(event.target.value)} placeholder="e.g. Nf3" /></label>
      <small>Use legal move notation for the side to move. This is your study idea, not an engine recommendation.</small>
      <div className="position-actions"><button type="submit" disabled={saving || disabled}>{saving ? 'Saving…' : 'Save position'}</button><button type="button" disabled={saving} onClick={() => { setOpen(false); setError(null); }}>Cancel</button></div>
    </form>}
    {error && <p role="alert" className="explorer-error">{error}</p>}
  </div>;
}
