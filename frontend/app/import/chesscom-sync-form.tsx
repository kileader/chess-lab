'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '../../lib/api-client';
import { emptySyncProgress, runChessComSync, type SyncProgress } from '../../lib/chesscom-sync';
import { practiceError } from '../practice-position';

export function ChessComSyncForm({ usernames, initialUsername, dateFrom, dateTo }: {
  usernames: string[]; initialUsername: string; dateFrom: string; dateTo: string;
}) {
  const router = useRouter();
  const [username, setUsername] = useState(initialUsername);
  const [from, setFrom] = useState(dateFrom);
  const [to, setTo] = useState(dateTo);
  const [speed, setSpeed] = useState('rapid');
  const [pending, setPending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [progress, setProgress] = useState<SyncProgress | null>(null);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => { stop.current = true; active.current?.abort(); }, []);

  async function sync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    stop.current = false;
    setPending(true); setStopping(false); setFinished(false); setError(null); setProgress(emptySyncProgress());
    try {
      await runChessComSync({ username, date_from: from, date_to: to, time_class: speed }, async (path, body) => {
        const response = await apiFetch(path, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body), signal: controller.signal,
        });
        if (!response.ok) throw new Error(await practiceError(response, 'Could not sync games. Try again.'));
        return response.json();
      }, setProgress, () => stop.current);
      setFinished(true);
    } catch (problem) {
      if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : 'Could not sync games.');
    } finally {
      active.current = null;
      if (!controller.signal.aborted) { setPending(false); router.refresh(); }
    }
  }

  if (!usernames.length) return <p className="sync-notice">First <Link href="/settings">add your Chess.com username</Link>. Lichess and Other games can still be uploaded as PGNs below.</p>;

  return <form className="position-form sync-form" onSubmit={(event) => void sync(event)}>
    <fieldset disabled={pending}>
      <legend>Download your completed games</legend>
      <label>Chess.com username<select value={username} onChange={(event) => setUsername(event.target.value)} required>
        {usernames.map((name) => <option value={name} key={name}>{name}</option>)}
      </select></label>
      <div className="sync-dates">
        <label>From<input type="date" required min="2007-01-01" max={to || dateTo} value={from} onChange={(event) => setFrom(event.target.value)} /></label>
        <label>Through<input type="date" required min={from || '2007-01-01'} max={dateTo} value={to} onChange={(event) => setTo(event.target.value)} /></label>
      </div>
      <label>Time control<select value={speed} onChange={(event) => setSpeed(event.target.value)}>
        <option value="rapid">Rapid</option><option value="blitz">Blitz</option><option value="bullet">Bullet</option><option value="daily">Daily</option><option value="all">All time controls</option>
      </select></label>
      <small>Standard chess only. Dates include both endpoints and use when a game ended (UTC). No Chess.com password needed.</small>
      <button className="auth-button" type="submit">{pending ? 'Syncing games…' : error || progress?.stopped ? 'Retry sync games' : 'Sync games'}</button>
    </fieldset>
    {pending && <button className="identity-remove" type="button" disabled={stopping} onClick={() => { stop.current = true; setStopping(true); }}>Stop after current month</button>}
    {progress && <div className="sync-progress" role="status" aria-live="polite">
      <strong>{pending ? stopping ? 'Stopping after this request…' : progress.currentMonth ? `Importing ${progress.currentMonth}…` : 'Checking available archives…' : error ? 'Sync interrupted' : progress.stopped ? 'Sync stopped' : 'Sync complete'}</strong>
      {progress.total > 0 && <><progress aria-label="Months imported" max={progress.total} value={progress.completed} /><span>{progress.completed} of {progress.total} months checked</span></>}
      <p>{progress.games_added.toLocaleString()} added · {progress.duplicates_skipped.toLocaleString()} already present · {progress.filtered_games.toLocaleString()} outside these dates, time control, or standard chess</p>
      {finished && !progress.stopped && progress.games_received === 0 && <p>No completed standard games matched this selection. Check your username, dates, and time control.</p>}
      {finished && progress.games_received > 0 && progress.matched_games === 0 && <p>Your imports were kept, but both sides match your saved names. <Link href="/settings">Check your usernames</Link> to include them in personal stats.</p>}
      {!pending && <Link href="/?period=all">View your dashboard — all dates →</Link>}
    </div>}
    {error && <p className="upload-error" role="alert">{error} Completed months are saved. Retrying skips duplicates, including a month saved before a connection dropped.</p>}
    <p className="sync-notice">Keep this page open while syncing. Games are saved month by month into your private library. This is a manual sync, not a scheduled import. Chess.com caches its archives, so recent games may appear later.</p>
  </form>;
}
