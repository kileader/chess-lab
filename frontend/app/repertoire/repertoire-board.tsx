'use client';

import { FormEvent, useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api-client';

export type RepertoireItem = {
  id: number;
  context: string;
  opening: string;
  status: 'keep' | 'practice' | 'try';
  note: string;
};

type Draft = Omit<RepertoireItem, 'id'>;
type OpeningStats = { games: number; wins: number; draws: number; losses: number };

const blankDraft: Draft = { context: '', opening: '', status: 'try', note: '' };
const statusCopy = { keep: 'Keep', practice: 'Practice', try: 'Try it' } as const;

export function RepertoireBoard({ initialItems, userId }: { initialItems: RepertoireItem[]; userId: number }) {
  const [items, setItems] = useState(initialItems);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [stats, setStats] = useState<Record<number, OpeningStats | null>>({});
  const contexts = [...new Set(items.map((item) => item.context))];

  async function loadStats(currentItems: RepertoireItem[]) {
    const pairs = await Promise.all(currentItems.map(async (item) => {
      try {
        const response = await apiFetch(`/api/users/${userId}/openings/detail?family=${encodeURIComponent(item.opening)}`);
        if (!response.ok) return [item.id, null] as const;
        const detail = await response.json() as OpeningStats;
        return [item.id, detail] as const;
      } catch {
        return [item.id, null] as const;
      }
    }));
    setStats(Object.fromEntries(pairs));
  }

  useEffect(() => { void loadStats(initialItems); }, [initialItems]);

  function changeDraft(field: keyof Draft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  function startEdit(item: RepertoireItem) {
    setEditingId(item.id);
    setDraft({ context: item.context, opening: item.opening, status: item.status, note: item.note });
    setShowEditor(true);
    setMessage(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(blankDraft);
    setShowEditor(false);
    setMessage(null);
  }

  async function saveItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.context.trim() || !draft.opening.trim()) return;
    setSaving(true);
    setMessage(null);
    try {
      if (editingId === null) {
        const response = await apiFetch(`/api/users/${userId}/repertoire`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([draft]),
        });
        if (!response.ok) throw new Error();
        const saved = await response.json() as RepertoireItem[];
        setItems(saved);
        void loadStats(saved);
      } else {
        const response = await apiFetch(`/api/users/${userId}/repertoire/${editingId}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft),
        });
        if (!response.ok) throw new Error();
        const updated = await response.json() as RepertoireItem;
        setItems((current) => {
          const saved = current.map((item) => item.id === updated.id ? updated : item);
          void loadStats(saved);
          return saved;
        });
      }
      cancelEdit();
    } catch {
      setMessage('Could not save that entry. Is the local API running?');
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem(itemId: number) {
    setSaving(true);
    setMessage(null);
    try {
      const response = await apiFetch(`/api/users/${userId}/repertoire/${itemId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error();
      setItems((current) => current.filter((item) => item.id !== itemId));
      if (editingId === itemId) cancelEdit();
    } catch {
      setMessage('Could not remove that entry. Is the local API running?');
    } finally {
      setSaving(false);
    }
  }

  const experiment = items.find((item) => item.status === 'try');
  const score = (entry: OpeningStats) => ((entry.wins + entry.draws / 2) / entry.games) * 100;

  return <>
    {experiment && <section className="experiment-panel panel">
      <div><p className="eyebrow">One thing to test</p><h2>{experiment.opening}</h2><p>{experiment.note || `You have marked this as something to try in ${experiment.context}.`}</p></div>
      <a href={`/openings/${encodeURIComponent(experiment.opening)}`}>See your games →</a>
    </section>}

    <section className="repertoire-editor panel" aria-labelledby="repertoire-editor-title">
      {!showEditor && <div className="repertoire-editor-closed"><div><p className="eyebrow">Change your plan</p><h2 id="repertoire-editor-title">Add another opening or situation.</h2></div><button type="button" onClick={() => setShowEditor(true)}>Add an opening</button></div>}
      {showEditor && <>
      <div className="panel-heading"><div><p className="eyebrow">Make it yours</p><h2 id="repertoire-editor-title">{editingId === null ? 'Add an opening' : 'Edit opening'}</h2></div></div>
      <form className="repertoire-form" onSubmit={saveItem}>
        <label>Situation<input value={draft.context} onChange={(event) => changeDraft('context', event.target.value)} placeholder="e.g. As White vs 1...c5" maxLength={80} required /></label>
        <label>Opening<input value={draft.opening} onChange={(event) => changeDraft('opening', event.target.value)} placeholder="e.g. Alapin Sicilian" maxLength={160} required /></label>
        <label>Status<select value={draft.status} onChange={(event) => changeDraft('status', event.target.value)}><option value="keep">Keep</option><option value="practice">Practice</option><option value="try">Try it</option></select></label>
        <label className="repertoire-note-field">Your note<textarea value={draft.note} onChange={(event) => changeDraft('note', event.target.value)} placeholder="What are you trying to learn or decide?" maxLength={500} rows={2} /></label>
        <div className="repertoire-actions"><button type="submit" disabled={saving}>{saving ? 'Saving…' : editingId === null ? 'Add to plan' : 'Save changes'}</button>{editingId !== null && <button type="button" className="button-quiet" onClick={cancelEdit}>Cancel</button>}</div>
      </form>
      {message && <p className="repertoire-message" role="status">{message}</p>}
      </>}
    </section>

    {items.length === 0 ? <section className="panel repertoire-empty"><h2>Your plan is empty.</h2><p>Add the first opening you want to keep, practice, or try.</p></section> : <section className="repertoire-grid" aria-label="Opening repertoire">
      {contexts.map((context) => <article className="panel repertoire-lane" key={context}>
        <div className="panel-heading"><div><p className="eyebrow">Your situation</p><h2>{context}</h2></div></div>
        <div className="repertoire-list">{items.filter((item) => item.context === context).map((item) => <div className="repertoire-item" key={item.id}>
          <span className={`repertoire-status status-${item.status}`}>{statusCopy[item.status]}</span>
          <a href={`/openings/${encodeURIComponent(item.opening)}`}><strong>{item.opening}</strong><p>{item.note || 'No note yet.'}</p>{stats[item.id] ? <small>{stats[item.id]!.games} games · {score(stats[item.id]!).toFixed(1)}% score</small> : <small>Not in your game data yet</small>}</a>
          <div className="repertoire-item-actions"><button type="button" onClick={() => startEdit(item)}>Edit</button><button type="button" onClick={() => deleteItem(item.id)} disabled={saving}>Remove</button></div>
        </div>)}</div>
      </article>)}
    </section>}
  </>;
}
