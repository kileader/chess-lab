'use client';

import { useState, type FormEvent } from 'react';
import { apiFetch } from '../../lib/api-client';
import { practiceError } from '../practice-position';

export function SetupForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true); setError(null);
    try {
      const response = await apiFetch('/api/account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(data)) });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not save your profile.'));
      window.location.assign('/');
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not save your profile.'); setPending(false); }
  }
  return <form className="position-form" onSubmit={(event) => void submit(event)}>
    <label>Display name<input name="display_name" required maxLength={80} autoComplete="nickname" disabled={pending} /></label>
    <label>Chess platform<select name="platform" disabled={pending}><option value="lichess">Lichess</option><option value="chess_com">Chess.com</option></select></label>
    <label>Chess username<input name="username" required maxLength={40} pattern="[A-Za-z0-9_\-]+" autoComplete="off" disabled={pending} /></label>
    <small>Start with one chess account. Use its exact username so we can identify your games.</small>
    <button className="auth-button" disabled={pending}>{pending ? 'Saving…' : 'Open my workspace'}</button>
    {error && <p role="alert" className="explorer-error">{error}</p>}
  </form>;
}
