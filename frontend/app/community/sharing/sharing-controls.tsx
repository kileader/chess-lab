'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiFetch } from '../../../lib/api-client';
import type { SharingSettings, ShareableGame } from '../../../lib/community';
import { practiceError } from '../../practice-position';

export function SharingControls({ initial, games }: { initial: SharingSettings; games: ShareableGame[] }) {
  const router = useRouter();
  const [name, setName] = useState(initial.name), [bio, setBio] = useState(initial.bio);
  const [visible, setVisible] = useState(initial.visible);
  const [saved, setSaved] = useState(initial);
  const [pending, setPending] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  async function save(event: FormEvent) {
    event.preventDefault(); setPending(true); setError(''); setMessage('');
    try {
      const response = await apiFetch('/api/account/sharing', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, bio, visible }) });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not save your sharing settings.'));
      const result = await response.json() as SharingSettings;
      setSaved(result);
      setMessage(result.visible ? 'Your profile is public. Games remain private until you share them below.' : 'Your profile is hidden and all game shares have been removed. Your private games are unchanged.');
      router.refresh();
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not save settings.'); }
    finally { setPending(false); }
  }
  return <>
    <form className="community-card position-form" onSubmit={save}>
      <h2>Your community profile</h2><p>Choose a public name. It does not have to match your Google name or chess username.</p>
      <fieldset disabled={pending} className="community-fields">
        <label>Public name<input required maxLength={60} value={name} onChange={event => setName(event.target.value)} /></label>
        <label>Short bio (optional)<textarea maxLength={240} rows={3} value={bio} onChange={event => setBio(event.target.value)} placeholder="What are you working on in chess?" /></label>
        <label className="community-checkbox"><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />Make my name and bio public to anyone, including visitors without an account.</label>
        <p className="identity-notice">Unchecking this and saving removes all game shares too. Turning it back on will not republish them. People may keep screenshots or copies of anything you publish.</p>
        <button className="auth-button" type="submit">{pending ? 'Saving…' : visible ? 'Save public profile' : 'Save hidden profile'}</button>
      </fieldset>
      {saved.visible && saved.public_id && <Link className="sync-import-link" href={`/community/players/${saved.public_id}`}>View your public profile →</Link>}
      {message && <p role="status">{message}</p>}{error && <p role="alert" className="explorer-error">{error}</p>}
    </form>
    <section className="community-library" aria-labelledby="choose-games"><h2 id="choose-games">Choose games from your private library</h2>
      <p>Sharing publishes both players’ names and ratings, the date, result, opening, time control, source platform, mainline moves, and your caption. PGN comments, variations, and private notes stay private. Up to 100 shared games.</p>
      {!saved.visible && <p>Publish your profile above to enable sharing.</p>}
      <div className="community-stack">{games.map(game => <ShareGame key={game.id} game={game} enabled={saved.visible && !pending} />)}</div>
    </section>
  </>;
}

function ShareGame({ game, enabled }: { game: ShareableGame; enabled: boolean }) {
  const router = useRouter();
  const [caption, setCaption] = useState(game.caption ?? ''), [shareId, setShareId] = useState(game.share_id);
  const [pending, setPending] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  async function change(remove: boolean) {
    setPending(true); setError(''); setMessage('');
    try {
      const response = await apiFetch(`/api/account/sharing/games/${game.id}`, remove ? { method: 'DELETE' } : {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ caption }),
      });
      if (!response.ok) throw new Error(await practiceError(response, 'Could not change game sharing.'));
      const result = await response.json() as { public_id?: string };
      setShareId(remove ? null : result.public_id!);
      setMessage(remove ? 'Unshared. Your private game is unchanged.' : 'Shared publicly. Open the shared game to copy its link.');
      router.refresh();
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not change sharing.'); }
    finally { setPending(false); }
  }
  return <form className="community-card position-form" onSubmit={event => { event.preventDefault(); void change(false); }}>
    <p className="eyebrow">{shareId ? 'Publicly shared' : 'Private'}</p><h3>{game.white ?? 'Unknown'} vs {game.black ?? 'Unknown'}</h3>
    <p>{game.opening ?? 'Unclassified opening'} · {game.result ?? 'Unknown result'} · {game.date ?? 'Undated'}</p>
    <label>Public caption (optional)<textarea disabled={!enabled || pending} maxLength={280} rows={2} value={caption} onChange={event => setCaption(event.target.value)} placeholder="What made this game interesting?" /></label>
    <div className="community-share-actions"><button type="submit" className="auth-button" disabled={!enabled || pending}>{pending ? 'Saving…' : shareId ? 'Update public caption' : 'Share this game publicly'}</button>
      {shareId && <><button type="button" className="identity-remove" disabled={pending} onClick={() => void change(true)}>Unshare</button><Link href={`/community/games/${shareId}`}>View shared game →</Link></>}
    </div>{message && <p role="status">{message}</p>}{error && <p role="alert" className="explorer-error">{error}</p>}
  </form>;
}
