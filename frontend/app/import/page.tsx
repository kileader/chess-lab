import Link from 'next/link';
import { requireAccount } from '../../lib/api-server';
import { authEnabled } from '../../lib/auth-config';
import { defaultSyncDates } from '../../lib/chesscom-sync';
import { AccountMenu } from '../account-menu';
import { UploadForm } from '../upload-form';
import { ChessComSyncForm } from './chesscom-sync-form';

export const dynamic = 'force-dynamic';

export default async function ImportGames({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const account = await requireAccount();
  const params = await searchParams;
  const usernames = account.identities.filter((identity) => identity.platform === 'chess_com').map((identity) => identity.username);
  const initialUsername = usernames.find((name) => name === params.username) ?? usernames[0] ?? '';
  const dates = defaultSyncDates(new Date());
  return <main className="connection-shell"><section className="connection-card auth-card import-card">
    <Link className="settings-back" href="/">← Back to your dashboard</Link>
    <p className="eyebrow">Your private library</p><h1>Import games.</h1>
    <h2>Sync from Chess.com</h2>
    {authEnabled() ? <ChessComSyncForm usernames={usernames} initialUsername={initialUsername} dateFrom={dates.date_from} dateTo={dates.date_to} /> : <p>Sign in with Google to sync Chess.com games. Local PGN uploads remain available.</p>}
    <section className="sync-upload"><h2>Or upload a PGN</h2><p>Lichess, Chess.com, and other standard PGN archives. Existing games are skipped automatically.</p><UploadForm /></section>
    <AccountMenu />
  </section></main>;
}
