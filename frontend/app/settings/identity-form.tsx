'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '../../lib/api-client';
import type { Account } from '../../lib/api-server';
import { practiceError } from '../practice-position';

type Identity = Account['identities'][number];

export function IdentityForm({ initialIdentities }: { initialIdentities: Identity[] }) {
  const router = useRouter();
  const initial = initialIdentities.length ? initialIdentities : [{ platform: 'lichess', username: '' }];
  const [rows, setRows] = useState(initial.map((identity, key) => ({ ...identity, key })));
  const [nextKey, setNextKey] = useState(initial.length);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  function update(key: number, field: keyof Identity, value: string) {
    setRows(rows.map((row) => row.key === key ? { ...row, [field]: value } : row));
    setMessage(null); setError(null);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setError(null); setMessage(null);
    try {
      const identities = rows.map(({ platform, username }) => ({ platform, username: username.trim() }));
      const response = await apiFetch('/api/account/identities', {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identities }),
      });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not save your usernames.'));
      const result = await response.json() as { account: Account; library_games: number; matched_games: number };
      setRows(result.account.identities.map((identity, key) => ({ ...identity, key })));
      setNextKey(result.account.identities.length);
      const unmatched = result.library_games - result.matched_games;
      setMessage(`Saved. ${result.matched_games.toLocaleString()} of ${result.library_games.toLocaleString()} imported games match one side.${unmatched ? ` ${unmatched.toLocaleString()} remain in your library but are excluded from personal stats because neither side or both sides match.` : ''}`);
      router.refresh();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not save your usernames.');
    } finally { setPending(false); }
  }
  return <form className="position-form identity-form" onSubmit={(event) => void save(event)}>
    <fieldset disabled={pending}>
      <legend>Accounts you play on</legend>
      {rows.map((row, index) => <div className="identity-row" key={row.key}>
        <label>Platform {index + 1}<select value={row.platform} onChange={(event) => update(row.key, 'platform', event.target.value)}><option value="lichess">Lichess</option><option value="chess_com">Chess.com</option></select></label>
        <label>Username {index + 1}<input required maxLength={40} pattern="[A-Za-z0-9_\-]+" autoComplete="off" spellCheck={false} value={row.username} onChange={(event) => update(row.key, 'username', event.target.value)} /></label>
        <button type="button" className="identity-remove" disabled={rows.length === 1} aria-label={`Remove username ${index + 1}`} onClick={() => { setRows(rows.filter((item) => item.key !== row.key)); setMessage(null); setError(null); }}>Remove</button>
      </div>)}
      <button type="button" className="identity-add" disabled={rows.length >= 10} onClick={() => { setRows([...rows, { key: nextKey, platform: 'lichess', username: '' }]); setNextKey(nextKey + 1); setMessage(null); }}>+ Add username</button>
    </fieldset>
    <small>Up to 10 usernames, including multiple on the same site. Capitalization doesn’t matter. Use your chess username, not your Google or Discord display name.</small>
    <p className="identity-notice">Saving recalculates matches in your existing private library. Removing or correcting a username may change your stats, but never deletes imported games, saved positions, or notes. Games matching both sides are excluded from personal stats.</p>
    <button className="auth-button" disabled={pending}>{pending ? 'Saving and matching games…' : 'Save usernames'}</button>
    {message && <p role="status" className="identity-status">{message}</p>}
    {error && <p role="alert" className="explorer-error">{error}</p>}
  </form>;
}
