import Link from 'next/link';
import { requireAccount } from '../../lib/api-server';
import { authEnabled } from '../../lib/auth-config';
import { defaultSyncDates } from '../../lib/game-sync';
import { AccountMenu } from '../account-menu';
import { UploadForm } from '../upload-form';
import { SyncForm } from './sync-form';

export const dynamic = 'force-dynamic';

export default async function ImportGames({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const account = await requireAccount();
  const params = await searchParams;
  const provider = params.platform === 'lichess' ? 'lichess' : params.platform === 'chess_com' ? 'chess-com'
    : account.identities.some((identity) => identity.platform === 'chess_com') ? 'chess-com' : 'lichess';
  const platform = provider === 'lichess' ? 'lichess' : 'chess_com';
  const usernames = account.identities.filter((identity) => identity.platform === platform).map((identity) => identity.username);
  const initialUsername = usernames.find((name) => name === params.username) ?? usernames[0] ?? '';
  const dates = defaultSyncDates(new Date());
  return <main className="connection-shell"><section className="connection-card auth-card import-card">
    <Link className="settings-back" href="/">← Back to your dashboard</Link>
    <p className="eyebrow">Your private library</p><h1>Import games.</h1>
    <div className="sync-providers" aria-label="Import platform"><Link aria-current={platform === 'chess_com' ? 'page' : undefined} href="/import?platform=chess_com">Chess.com</Link><Link aria-current={platform === 'lichess' ? 'page' : undefined} href="/import?platform=lichess">Lichess</Link></div>
    <h2>Sync from {provider === 'lichess' ? 'Lichess' : 'Chess.com'}</h2>
    {authEnabled() ? <SyncForm key={`${provider}:${initialUsername}`} provider={provider} usernames={usernames} initialUsername={initialUsername} dateFrom={dates.date_from} dateTo={dates.date_to} /> : <p>Sign in with Google to sync games. Local PGN uploads remain available.</p>}
    <section className="sync-upload"><h2>Or upload a PGN</h2><p>Lichess, Chess.com, and other standard PGN archives. Existing games are skipped automatically.</p><UploadForm /></section>
    <AccountMenu />
  </section></main>;
}
